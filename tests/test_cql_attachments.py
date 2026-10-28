import httpx
from tests.test_confluence_jobs import setup_client, config, enqueue
from tests.test_pptx import presentation_bytes


def test_cql_multiple_presentations_update_without_duplicate_objects(tmp_path):
    state = {'version': 1, 'broken': False}
    content = presentation_bytes()
    def attachment(aid):
        return {'id': aid, 'type': 'attachment', 'title': ('Renamed' if state['version'] == 2 else 'Decision') + aid + '.pptx',
                'container': {'id': '1'}, 'version': {'number': state['version']},
                '_links': {'download': '/download/attachments/1/' + aid + '.pptx'}}
    def handler(req):
        path = req.url.path
        if path.endswith('/search'):
            return httpx.Response(200, json={'results': [{'id': '1', 'type': 'page', 'title': 'Committee'}, {'id': '2', 'type': 'page', 'title': 'Empty'}]})
        if path.endswith('/child/attachment'):
            if '/2/' in path: return httpx.Response(200, json={'results': []})
            start = req.url.params.get('start')
            if start == '0': return httpx.Response(200, json={'results': [attachment('att11')], '_links': {'next': '/ignored'}})
            return httpx.Response(200, json={'results': [attachment('att12'), attachment('att13')]})
        if '/download/' in path:
            assert req.url.params['version'] == str(state['version'])
            if state['broken'] and 'att12' in path: return httpx.Response(503)
            return httpx.Response(200, content=content)
        return httpx.Response(200, json=attachment(path.rsplit('/', 1)[-1]))

    app, client, _ = setup_client(tmp_path, handler)
    with client:
        connection, type_id = config(client)
        def run():
            job = enqueue(client, connection, type_id, source_mode='attachments').json()
            app.state.confluence_worker.run_once()
            return client.get('/api/confluence/jobs/' + job['id']).json()
        first = run()
        assert first['status'] == 'succeeded', first
        items = [i for i in first['items'] if i.get('attachment_id')]
        assert len(items) == 3
        pending_repeat = run()
        assert [i['candidate_id'] for i in pending_repeat['items'] if i.get('attachment_id')] == [i['candidate_id'] for i in items]
        assert next(i for i in first['items'] if i['page_id'] == '2')['attachment_count'] == 0
        ids = {}
        for item in items:
            candidate = client.get('/api/candidates/' + item['candidate_id']).json()
            assert candidate['target_id'] is None
            result = client.post('/api/candidates/' + candidate['id'] + '/review', json={'expected_revision': 0, 'fields': {'title': item['title']}, 'status': 'published'})
            assert result.status_code == 200, result.text
            ids[item['attachment_id']] = result.json()['id']
        repeated = run()
        assert [i['candidate_id'] for i in repeated['items'] if i.get('attachment_id')] == [i['candidate_id'] for i in items]
        state.update(version=2, broken=True)
        updated = run()
        assert updated['status'] == 'partial'
        for item in updated['items']:
            if item.get('attachment_id') and item['status'] == 'succeeded':
                candidate = client.get('/api/candidates/' + item['candidate_id']).json()
                assert candidate['target_id'] == ids[item['attachment_id']]
                assert candidate['source_metadata']['version'] == 2
                accepted = client.post('/api/candidates/' + candidate['id'] + '/review', json={'expected_revision': candidate['base_revision'], 'fields': {'title': item['title']}, 'status': 'published'})
                assert accepted.status_code == 200, accepted.text
                assert accepted.json()['id'] == ids[item['attachment_id']]
                assert accepted.json()['revision'] == 2
        state['broken'] = False
        retry = client.post('/api/confluence/jobs/' + updated['id'] + '/retry').json()
        assert len(retry['items']) == 1 and retry['items'][0]['attachment_id'] == 'att12'
        app.state.confluence_worker.run_once()
        assert client.get('/api/confluence/jobs/' + retry['id']).json()['status'] == 'succeeded'
        assert len(client.get('/api/artifacts').json()) == 3
