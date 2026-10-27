# Проверка первой итерации — 27.10.2026

Область: ручной реестр + HTML; Confluence отложен пользователем.

## Автоматические проверки

- Первый RED: pytest не мог импортировать отсутствующий `backend.app.main` до реализации.
- После реализации: 12 API/integration tests PASS на реальной SQLite с миграциями и временными исходниками.
- После независимого ревью: три новых регрессии воспроизвели ошибки, затем весь набор — **15 PASS**.
- `npm.cmd --prefix frontend run build`: TypeScript проверен, production build Vite успешно собран.
- Есть предупреждение Starlette о будущем переходе TestClient с httpx на httpx2; текущий зафиксированный набор зависимостей проходит тесты.

Воспроизведённые случаи: неполный draft, валидация публикации, сохранение после перезапуска, неизменяемые версии схем, конкурирующее редактирование, защита localhost-запросов, FTS-запросы, экспорт, выбор таблицы, evidence и исходные байты, маркер внутри абзаца, отсутствующая граница, неоднозначные поля, сложные ячейки, активный HTML, пустой/неверный файл, повторная загрузка, ручные исправления, stale/superseded/rejected candidates, привязка после загрузки, возврат прежней версии, div и вложенные параграфы.

## Браузер и запуск

Playwright CLI, реальный Chromium, отдельные данные `output/browser-data` и `output/launcher-check`:

- Ручной ввод и публикация архитектурного решения.
- Прикрепление HTML к существующему объекту; извлечение шести полей.
- Текущее ручное значение остаётся в форме; отдельное применение владельца.
- Переход к исходному блоку и проверка цитаты после сохранения.
- Подтверждение создаёт ревизию 2; JSON содержит ожидаемые поля и ревизию.
- Регрессия: поиск больше не исключает объекты из списка привязки.
- Ширина 390 px: горизонтального переполнения нет; скриншот сохранён.
- После исправления favicon и итоговой перезагрузки — 0 ошибок/предупреждений консоли.
- `scripts/start.ps1 -NoBrowser -Port 8766 -DataDir ...` запускает сервер; изолированная база создаётся миграцией.
- Через этот launcher создан новый объект из HTML-разделов, проверены полный текст проблематики, сохранение после перезагрузки браузера и метод `section` в JSON-экспорте.

Артефакты: `output/playwright/registry.png`, `review.png`, `mobile.png`. Выходные файлы тестов исключены из Git.

## Что не подтверждено

Реальная интеграция Confluence, точность на корпоративных HTML, высокая нагрузка, установка на чистой Windows, автоматический backup/restore, LLM/PPTX/scripts. Проверка текущей машины не заменяет эти этапы.

## Дополнение: Confluence

Интеграция реализована в следующей итерации. Общий набор расширен до 35 проходящих тестов. Фактические проверки, условия и live-ограничения изложены в [confluence.md](confluence.md). Проверка доступа к реальному серверу по-прежнему не выполнена.

Ревью: выполнено независимо, три important проблемы исправлены с тестами; отдельная UI-проблема поиска исправлена с браузерной регрессией. Небольшая доработка доступности модального окна (focus trap/Escape) отложена.

## Дополнение: PPTX и пайплайны, версия0.3

- `.venv/Scripts/python.exe -m pytest -q --basetemp=output/pptx-final-tests` с `RUN_DOCKER_TESTS=1`: **52 passed**, одна прежняя deprecation warning Starlette/httpx.
- После добавления заключительных проверок: `tests/test_python_runtime.py`, `--basetemp=output/python-limits-final`, Docker включён. Проверяет SDK, UID/FS/network/cgroups, таймаут, output cap, недоступный runtime, evidence/schema, OOM/invalid JSON, Python между заголовками.
- `npm.cmd --prefix frontend run build`: TypeScript и production build успешны, приложение0.3.0.
- Браузер: `output/playwright/{pptx-upload,pipeline-flow,attachment-flow,params-regression}.js`. Два первоначальных прогона остановились на ошибочных локаторах сценария (getByLabel textarea и несуществующее имя кнопки цитаты); реальные UI-действия после уточнения snapshot завершены. На финальном прогоне0 ошибок/предупреждений консоли.
- Снимки: `pptx-review.png`, `pipeline-tested.png`, `pipeline-provenance.png`, `attachment-preview.png`, `pipelines-mobile.png`, `pipelines-final.png` в output/playwright.
- Review: один Important и один Minor исправлены, регрессии проверены; подробности в progress.md.
- Рабочее обновление: backup → проверка миграции на копии → рестарт при0 активных импортах → HTTP200/version0.3.0/runtime available → совпадение fingerprints исходных таблиц. Реальные данные не использовались в тестовых импортах, реальный Confluence не запрашивался.

## Дополнение: Ollama и поиск, версия0.4

- `RUN_DOCKER_TESTS=1 .venv/Scripts/python.exe -m pytest -q --basetemp=output/ollama-final-tests`: **71 passed**,1 прежняя Starlette/httpx deprecation warning.
- `tests/test_semantic_search.py --basetemp=output/search-labels-check`: **3 passed** после замены внутренних названий полей на пользовательские labels.
- `npm.cmd --prefix frontend run build -- --outDir ../output/ollama-dist`: TypeScript/Vite успешно; staged dist установлен только при обновлении сервиса.
- Реальные Ollama модели/время/качество: [ollama.md](ollama.md). Проверялся синтетический корпус, не пользовательские документы. Начальный индекс пользовательского реестра построен отдельно после обновления как рабочая функция.
- Браузерные сценарии: output/playwright/ollama-prepare.js, ollama-flow.js, ollama-final.js. Первый e2e assert ожидал обязательное автоматическое название; модель его пропустила. Сценарий продолжен через предусмотренную ручную коррекцию, без обхода серверной проверки. Все последующие шаги и повторное извлечение завершены; console0 errors/0 warnings.
- Скриншоты: ollama-settings.png, ollama-review.png, ollama-search.png, ollama-search-mobile.png, ollama-review-final.png, ollama-review-mobile-final.png.
- Review: Important typed-literal + Minor lexical ranking исправлены, новые тесты показали RED→GREEN. Реальный digest/размерность соответствуют индексированию1024.
- Backup + миграция на копии + сохранность рабочих строк после deployment + HTTP200/version0.4.0 + initial index2/2 подтверждены инструментами.

## OpenAI-compatible providers0.5 — 27.10.2026

- `pytest tests --basetemp=output/providers-release-tests`: **82 passed,6 skipped**, одна прежняя Starlette/httpx deprecation warning. Пропущенные6 — opt-in Docker isolation из прошлой итерации; Python runtime не изменялся. `tests/test_providers.py`:17проверок/параметризованных случаев; совместно с semantic tests20passed после последнего фикса.
- TypeScript/Vite0.5 staged build: `output/providers-dist`; установлен в frontend/dist только после backup. Новых runtime dependencies нет.
- Протокол mocks: правильный base path/Bearer, json_object/json_schema/text, standard token options, ошибки401/403/429/redirect без echo ключа, embeddings index ordering/dim/norm/overflow, обязательный review, LLM pipeline routing, key rotation/index isolation, manual alias без /models.
- Реальный стандартный API: `http://127.0.0.1:11434/v1`, только synthetic fixture llm-delivery.html и isolated registry output/providers-browser. Chat ornith44.537секунды: title/problem/tasks/owner с цитатами; ручное название сохранено после review. bge-m3:1024измерения,1/1объект; смысловой запрос вернул объект без буквального совпадения. Повторная индексация после fix building flag доступна.
- Browser screenshots: output/playwright/providers-{settings,search,search-mobile,mobile,final}.png. Desktop/mobile390 overflow отсутствует. В QA были исправлены локаторы wrapping-label и ожидание окончания review; после перезапуска QA обновлена browser session (старый local token ожидаемо403). Runtime JS ошибок не обнаружено; Chrome выдаёт verbose DOM diagnostic о password input вне form. Финальный повторный build проверен в свежей сессии.
- Временный synthetic credential set/get/delete через настоящий Windows Credential Manager успешен, ключ удалён. Ревью fresh-context без подтверждённых замечаний, см.progress.md.
- Backup output/release-backup-05-20261027-190509; migration0004→0005 на копии и рабочем сервисе; HTTP200/version0.5.0/new bundle подтверждены. Существующие registry/FTS/pipeline/index rows и blobs сравнены с backup; unchanged. Рабочий индекс сохранён без перестройки:1/2актуальны,stale1; это состояние до обновления, что подтверждено совпадением всех строк с backup. Первичная проверка с ожиданием2/2 остановилась на этом изменившемся baseline, затем выполнено полное сравнение данных. Внешних профилей0.
- Не проверены реальные внешние OpenRouter/LiteLLM ключи, тарифы, корпоративные сертификаты/прокси. Результаты совместимого /v1 smoke не выдаются за проверку этих внешних аккаунтов.
