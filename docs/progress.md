# Выполнение docs/implementation_plan.md

Первая итерация (завершена): ручной реестр и HTML (задачи 1–3), поиск/JSON для использования результата. Реализация следующей итерации Confluence описана в конце этого файла.

- Подтверждён первый тип: «Архитектурное решение» (название, описание, проблематика, задачи проекта, решение, владелец).
- Ruling: Git отсутствует; работаем в текущем новом каталоге без создания worktree и коммитов.
- Ruling: эталонные документы пока синтетические; реальные документы и 20 примеров пилота остаются к приёмке.
- Ruling: загрузка одного HTML синхронная и ограничена размером; массовая очередь/worker относятся к следующей интеграции Confluence.
- Pre-flight: parse_html → NormalizedDocument → proposals → candidate → review → ArtifactRevision. UUID, version и JSON field paths одинаковы на границах.
- Задача 1: реализованы ручной реестр, draft/published, версии схем, история ревизий и launcher.
- Задача 2: реализованы HTML snapshots, нормализованный документ, table/sections, evidence. Объединённые/вложенные ячейки пока явно пропускаются.
- Задача 3: реализованы одиночная проверка, привязка, сравнение baseline/current/proposed, retry, конфликт ревизий. Массовое подтверждение остаётся к этапу массового импорта.
- Из задачи 5 реализованы FTS5 и JSON-экспорт; автоматический backup ещё не реализован, в README описана копия остановленного реестра.
- Ruling: поиск, JSON и простая версия схем включены в этот срез, чтобы результат ручного/HTML-ввода можно было использовать. Корпус реальных документов и нагрузочный пилот остаются перед расширением.
- Независимый read-only review выполнен агентом mvp_review. Все три important findings получили воспроизводящие failing tests, исправления и успешный полный прогон (15 tests).
- Final fixed: новый target при совпадающих байтах — test_bind_after_unbound_upload_retargets_pending_candidate RED→GREEN.
- Final fixed: reprocess после reject / возврата A→B→A — test_reprocess_rejected_and_reverted_source RED→GREEN.
- Final fixed: текст div и nested paragraphs — test_section_preserves_div_text_and_does_not_duplicate_nested_paragraph RED→GREEN.
- Final ruling: фильтр поиска скрывал объекты в списке привязки; повышено до important, так как блокировало допустимое действие. Воспроизведено браузером, исправлено отдельным allItems, браузерная регрессия прошла.
- Final minor (deferred): полный focus trap/Escape/возврат фокуса у диалога цитаты; сейчас есть кнопка закрытия и начальный фокус.
- Браузер: ручная публикация, HTML→существующий объект, отдельное применение поля, сохранение ручной проблематики, цитата, экспорт, фильтр и mobile 390 px проверены. Скриншоты и временные сценарии в output/playwright.
- Особенность среды: обычная песочница Windows зависает на asyncio socketpair (faulthandler traceback); тесты и сервис проходят вне неё. Временные тестовые данные находятся только в output/.

## Итерация Confluence — 27.10.2026

Пользователь авторизовал CQL, загрузку страниц и предложения; уточнил on-premise 7.13.7 и PAT. Реальный URL/PAT не передавались.

- Ruling: поддерживается DC REST + PAT; Cloud не добавлялся. URL вводится в приложении. Стоимость неверного допущения — другой адаптер, но редакция подтверждена пользователем.
- Ruling: worker реализован фоновым потоком локального API вместо отдельного процесса. Очередь, lease и результаты персистентны; возможна задержка возобновления до 60 секунд после аварийного завершения.
- Ruling: preview ограничен 500 страницами с явным предупреждением. Большие реестры обрабатываются более узкими CQL-выборками.
- Реализованы миграция 0002, Windows Credential Manager, CQL pagination/dedup, origin-restricted REST, bounded HTTP retry, storage parser, stable resource IDs, versioned snapshots, jobs/cancel/retry/recovery, Confluence UI и интеграция Review.
- Pre-flight: страницы не дедуплицируются по содержимому; page ID вместе с connection ID определяет источник. Смена версии схемы того же типа явно блокируется для уже связанного объекта, чтобы не создавать дубль вместо миграции.
- Новые тесты сначала RED (отсутствие модулей), затем GREEN. Дополнительные регрессии RED→GREEN: XHTML entities, interrupted blob, схема v1→v2.
- Независимый read-only review confluence_review выявил эти три important случая; исправлены. Общий счётчик предложений повышен с minor до исправляемой проблемы, так как показывал 0 при готовых кандидатах; воспроизведён браузером и исправлен, проверено обновление 2→3 при retry.
- Полный suite: 35 PASS. TypeScript и Vite production build PASS. Starlette выдаёт известное предупреждение о httpx→httpx2, тесты работают с зафиксированными зависимостями.
- Реальный Windows Credential Manager smoke test PASS: set/read/replace/delete, синтетическая запись удалена.
- Миграция копии предыдущей БД: 0001→0002, количество существующих объектов 1→1.
- Browser QA на явном имитаторе: CQL pagination, 3 страницы, частичный 403, retry только page 103, отсутствие объектов до review, цитата, ручная коррекция и публикация с разными методами provenance; ошибок консоли нет.
- Не проверены: реальный Confluence, корпоративный CA/VPN/SSO и нестандартные макросы пользователя. Не реализованы в этом этапе: ручная привязка page ID к ранее созданному вручную объекту в UI, миграции схем, независимые именованные профили. Созданные этим импортом объекты обновляются без дублей.

## Итерация 0.3 — PPTX и редактор правил/Python (27.10.2026)

План: [pptx-pipelines-plan.md](pptx-pipelines-plan.md). Пользователь явно выбрал оба этапа; LLM остаётся вне области. Инструкция: [pptx-pipelines.md](pptx-pipelines.md).

- Реализованы локальная загрузка PPTX и REST-resolve/download Confluence-вложения, снимки, слайд/фигура/ячейка в evidence, supplementary source для объекта страницы и явный standalone.
- Добавлены версии пайплайнов, последовательный редактор table/sections/between/Python, проверка на снимках, diff и отдельная публикация. Опубликованный ID выбирается при HTML/PPTX/CQL импорте; можно повторно обработать сохранённый снимок.
- Python исполняется только в Docker: образ architecture-registry-python:1 собран локально. Публикация закрепляет image ID; версия исполняется по закреплённому образу. Нет host mounts/сети/секретов; лимиты описаны в инструкции.
- RED→GREEN: сначала отсутствующие модули, затем DTD в UTF-16 и неполный provenance; исправлены тестами. Дополнительно воспроизведён и исправлен дефект baseline по review.
- Независимый reviewer pptx_pipeline_review: Important — ошибка старого пайплайна блокирует публикацию исправленного; исправлено разделением baseline_error и результата новой версии. Minor — params редактора расходятся со steps после JSON/reorder; исправлено синхронизированным состоянием и проверено в браузере.
- Отступления от исходной структуры: компактные модули вместо директорий; JSON вместо YAML; загрузка отдельного вложения синхронная, без устойчивой очереди; stdout/stderr лимит 1 MiB вместо верхней границы 10 MiB. Эти решения описаны пользователю в инструкции. Исходные корпоративные PPTX не предоставлялись: проверялись синтетические презентации.
- Git-репозитория нет: worktree/commits не создавались; журнал ведётся здесь вместо git-зависимых sdd-скриптов.
- Проверки: полный набор до заключительных двух сценариев — 52 passed, включая 4 реальных Docker tests; отдельно заключительный набор Docker — 6 тестов (добавлены OOM/invalid JSON и Python между заголовками). Frontend TypeScript/Vite build прошёл.
- Browser QA: локальный PPTX → review; between + table + Python → тест → публикация → replay → объект → цитата; remote attachment на имитаторе → дополнение объекта без дубликата; JSON/reorder/invalid params; ширина390 без горизонтального overflow; console 0 errors/0 warnings. Артефакты в output/playwright.
- Рабочая БД сохранена в output/release-backup-03-20261027-181240 (SQLite backup API + blobs). Миграция0002→0003 сначала проверена на отдельной копии; существующие записи побитово по содержимому строк не изменились.
- Локальный сервис обновлён и открыт: http://127.0.0.1:8765, версия0.3.0, HTTP200, Docker available=true, PID21184. Каталог данных прежний: C:/Users/marat/AppData/Local/ArchitectureRegistryStudio. После обновления fingerprints существующих таблиц совпали с backup. QA-сервер8768 и тестовый браузер остановлены, временных arch-step контейнеров нет.
- Реальное подключение к корпоративному Confluence и его вложениям не проверялось. LLM/семантический поиск, OCR, автоматический backup и упаковка для чистой машины остаются следующими этапами.

## Итерация0.4 — Ollama и семантический поиск (27.10.2026)

План: [ollama-plan.md](ollama-plan.md); инструкция: [ollama.md](ollama.md). Пользователь авторизовал этап8 и выбрал ornith-1.5:9b; установленная bge-m3:latest используется для embeddings. Связанный поиск памяти не дал применимых проектных решений; факты о моделях проверены локально.

- Реализованы local-only Ollama adapter, structured proposals, валидация schema/evidence/literal, отдельная маркировка transformed, проверка model digest до/после вызова. Ollama доступна отдельным экраном и шагом версионируемого пайплайна.
- Ответы/ошибки не создают объектов без review. Принятые значения сохраняют model/digest/options/prompt hash/run ID. Сырые ответы успешных и отклонённых генераций ограничены размером и хранятся отдельно7 дней с lazy cleanup; метаданные принятых значений остаются в ревизии.
- Семантический индекс: SQLite generations, chunk1500/overlap200 с пользовательскими названиями полей, точный cosine, BM25+RRF, фильтры, исключение старых ревизий, fallback FTS. Смена поколения атомарна; сеть/модель не удерживают write transaction. Обновление пока явное кнопкой, не автоматическая фоновая задача.
- Ревью ollama_review: Important — нестроковые literal могли обходить проверку, теперь требуют transformed (RED→GREEN). Minor — FTS-ранги использовали updated_at; заменено на BM25. Новые raw-error и model-change контракты покрыты тестами.
- Реальная диагностика: первоначальная модель меняла регистр при mode=extracted; подтверждённая смена регистра теперь явно маркируется transformed, выдуманные значения по-прежнему отклоняются. Добавлены kind/level в prompt. На HTML с общей меткой «Решение» модель пропустила title; пользовательский review успешно заполнил его вручную. Не заявляется безошибочное извлечение.
- Проверки: полный suite с RUN_DOCKER_TESTS=1, output/ollama-final-tests —71 passed,1 прежняя deprecation warning. После замены внутренних ключей полей на пользовательские названия отдельно semantic tests —3 passed. Frontend0.4 production build прошёл в output/ollama-dist, не меняя рабочий frontend до обновления.
- Live smoke только на синтетических данных: ornith четыре поля за9.33с; bge-m3 dim1024,23.12с с загрузкой, related cosine0.547 > unrelated0.470. Браузер8769: upload→LLM→ручной review→объект, index→semantic query→релевантный объект первым, повторное извлечение не перезаписывает ручное название; capabilities фильтр моделей; mobile390 без overflow; console0 ошибок/предупреждений.
- Миграция0003→0004 проверена на копии всех существующих таблиц, fingerprints/rows неизменны. Backup: output/release-backup-04-20261027-184012 (SQLite backup API + blobs).
- Рабочий сервис http://127.0.0.1:8765 обновлён до0.4.0 (HTTP200), прежний каталог данных сохранён. Существующие строки всех таблиц, включая FTS, сравнились с backup без изменений. По авторизованному запросу создан производный индекс текущего реестра bge-m3:2/2 объектов,1024 измерения,stale0. Приложение открыто в браузере.
- Git/worktree отсутствуют в исходном проекте; изменения и проверка зафиксированы журналом, без git commits. Пиковая RAM/VRAM, корпоративный закрытый корпус, массовая фоновая индексация и другие провайдеры LLM не проверялись/не добавлены.

## Итерация0.5 — OpenAI-совместимые провайдеры (27.10.2026)

- Выполнен providers-plan.md: именованные immutable профили OpenRouter/LiteLLM/compatible, Windows Credential Manager namespace Providers, ротация/удаление ключа, отключение; HTTPS remote/HTTP loopback, no redirects/env proxy, статические ошибки без echo тела/ключа.
- Общая проверка цитат и review сохранены. Провайдер выбирается для прямого извлечения, embeddings и каждого LLM-шагa; HTML/PPTX/Confluence/replay/test baseline используют resolver текущего приложения. Профиль/actual response model записываются в provenance и индекс; конфигурационный fingerprint явно отличается от hash весов. Старые pipeline/index по умолчанию используют Ollama.
- UI «Модели и API», примеры base URL, необязательный каталог моделей, ручной alias, режимы JSON/text, параметры совместимости; явный адрес передачи текста/поиска. Выбор операций остаётся локальным по умолчанию, профиль сам по себе не отправляет документы.
- Ruling: metadata профиля не редактируется, изменение endpoint/deployment — новым профилем, ключ ротируется отдельно. Причина: ранее опубликованные пайплайны не должны незаметно отправлять документы на другой endpoint. Цена: переименование/настройки требуют нового подключения. Внешний API не даёт надёжного hash весов — замена под прежним alias требует ручной новой метки и переиндексации.
- TDD: отсутствие адаптера RED→8GREEN; появление embedding-model после первого ответа без model RED→GREEN; oversized int RED→GREEN. В визуальном QA обнаружен существующий building=true в успешном POST index; отдельный regression RED→GREEN, статус теперь читается после освобождения lock. Финальный backend82passed,6Docker tests skipped (runtime Python не менялся); staged TypeScript/Vite build успешен.
- Реальный Windows Credential Manager set/get/delete проверен только с временным синтетическим ключом; он удалён. Реальный OpenAI-compatible протокол проверен на локальном Ollama/v1, отдельный QA реестр8769: ornith44.537с,4поля; ручная правка→публикация; bge-m3 индекс1024; смысловой запрос без буквального совпадения→объект. Desktop/mobile390 без horizontal overflow; повторная индексация после фикса доступна.
- Fresh-context reviewer не выявил actionable defects; первоначальная претензия к JSX отозвана после перечитывания/TypeScript проверки. Последующие небольшие fixes numerical overflow/build lock подтверждены regression tests и browser.
- Backup output/release-backup-05-20261027-190509: SQLite backup + blobs; миграция0004→0005 на копии сохранила существующие таблицы. Рабочий8765 обновлён до0.5.0; HTTP200/version/bundle, все существующие registry/FTS/pipeline/index строки и blobs неизменны. Прежний Ollama index сохранён:1/2актуальны,stale1 из-за изменения объекта до обновления (строки индекса/объектов совпали с backup); автоматическая переиндексация не запускалась. Внешние профили не создавались в рабочем приложении.
- Ограничения: реальные OpenRouter/корпоративный LiteLLM с пользовательскими ключами не проверялись; нет нестандартных auth headers/custom CA/billing. Нет git-репозитория — без worktree/commit. Подробности подключения в providers.md.


## Итерация0.5.1 — инструкции и контекст LLM (27.10.2026)
- Добавлены prompt (до4000символов) и include_previous. Контекст содержит текущие проверенные поля/evidence, сводки предыдущих шагов и конфликты; raw/model metadata исключены. Старые шаги оставлены без контекста; новые в UI включают его. Схема ответа и цитаты проверяются прежним валидатором, контекст не является источником цитирования.
- Общий лимит12000байт включает инструкцию/контекст; silent truncation нет. Prompt hash учитывает новые данные. Изменения хранятся в новой версии, overwrite нужен для замены поля.
- TDD: новые сценарии сначала RED, затем11passed. Полный suite93passed/6Docker skipped; после добавления проверки immutable versions целевой набор12passed. TypeScript/Vite build успешно в output/context-dist. Fresh-context review без дефектов.
- Browser QA только output/context-browser: ввод prompt, default checkbox, сохранение, reload/reopen, mobile390 без overflow. Screenshot output/playwright/context-editor.png проверен визуально. Реальную генерацию/платные API повторно не вызывали; payload и проверки тестировались контролируемой моделью.
- Backup output/release-backup-051-20261027-211430; рабочий8765 обновлён0.5.1. HTTP200/new bundle и сравнение всех существующих таблиц (кроме TTL llm_outputs) с backup: unchanged. Схема БД0005 без новой миграции. QA сервер/браузер закрыты. Git/worktree отсутствуют, commits не создавались.
- Инструкция: docs/llm-step-context.md.


## Итерация0.5.2 — просмотр LLM-запросов (27.10.2026)
- Полная диагностика запроса/ответа сохраняется в TTL llm_outputs (7дней), включая actual OpenAI wire body, system/custom instruction/context и raw text/API JSON. HTTP headers/key не записываются. Старые raw-only записи явно обозначаются; запрос/ответ при сетевых ошибках может отсутствовать, oversized response256KiB помечается как omitted.
- Тестовый отчёт содержит ссылки для каждого шага текущей/baseline версии, включая успешные вызовы перед поздним сбоем и ошибочный вызов. UI загружает диагностику при раскрытии. Defaultprompt берётся из backend SYSTEM и заменяет текст редактируемой инструкции; сохранение новой версией, без запуска модели.
- TDD tests/test_llm_trace.py:4RED→4GREEN (wire body, API secrets absence, failed response, multi-step persistence). Полный suite98passed/6Docker skipped; TypeScript/Vite staged build successful. Fresh-context review без blocking findings.
- Browser QA изолированный output/trace-browser с synthetic controlled model: defaultprompt fill, custom instruction, save version, test, trace/input/context/raw assertions, mobile390 без overflow. Первый locator exact label не учёл textarea content; после уточнения сценарий завершён. Снимки output/playwright/trace-report.png и trace-detail.png; detail визуально проверен. Реальные внешние/платные вызовы не выполнялись.
- Backup output/release-backup-052-20261027-212141; deployment0.5.2 на8765: HTTP200, defaultprompt endpoint/new bundle; все существующие таблицы кроме TTL llm_outputs совпали с backup. Схема0005 без миграции. QA закрыт. Git отсутствует, без commits/worktrees. Инструкция docs/llm-diagnostics.md.


## Итерация0.6 — новые типы и конструктор (27.10.2026)
- Отдельная кнопка создания типа; название/ключ/описание, до40реквизитов, названия/ключи/виды/required/описания, строковые enum, JSON Schema режим. Сохранение новой версии оставляет предыдущие объекты/схемы неизменными. Constraint metadata сохраняются при обычных правках и roundtrip; смена вида явно сбрасывает специальные ограничения.
- Новый create_new flag защищает от конфликта ключа в BEGIN IMMEDIATE. Прежняя семантика POST без флага сохранена. Изменения БД не нужны (schema0005).
- Reviewer отметил возможность удалить title и получить безымянные объекты. Ruling: в новом типе обязательный строковый title — инвариант; защищён в конструкторе и create_new API, JSON сохранение UI также проверяет его. Прежний общий API версий совместим. Три регрессии RED→GREEN.
- Полный suite output/types-final-suite:103passed/6Docker skipped, прежняя deprecation warning. TypeScript/Vite0.6 build output/types-dist успешен. Fresh-context review без других замечаний.
- Browser QA только output/types-browser: новый тип information_system, строковый enum/обязательное поле, публикация объекта, JSON roundtrip minLength/maxLength, ошибки duplicate type/field keys, версия2 и неизменность объекта наv1, защищённый title, desktop/mobile390 без overflow. Первый exact textarea locator скорректирован; конечный сценарий успешен. Скриншоты output/playwright/types-builder.png и types-builder-mobile.png, desktop просмотрен визуально.
- Backup output/release-backup-06-20261027-214542; рабочий8765 обновлён0.6.0. HTTP200/version/new bundle и сравнение всех существующих таблиц (кроме TTL llm_outputs) с backup: unchanged. Тестовые типы/объекты в рабочем реестре не создавались. QA закрыт. Git отсутствует, без commits/worktrees.
- Инструкция docs/type-builder.md, план docs/type-builder-plan.md.


## Локальный Git и инструкция развёртывания (27.10.2026)
- По запросу пользователя инициализирован локальный репозиторий, ветка main. Удалённый репозиторий не создавался и remote не настраивался.
- README переписан: установка из исходников на Windows, Python3.13/Node22.12+, setup/start, параметры порта/каталога, Ollama/OpenAI-compatible/Confluence/Python runner, обновление, backup/restore и ограничения. Команды сверены с существующими скриптами и lock-файлами; чистая Windows в этой итерации не тестировалась.
- .gitignore дополнен: env variants, локальные исходные документы docs, ключи/сертификаты/логи. .gitattributes задаёт нормализацию текста. Проверены107кандидатов исходников,12локальных README ссылок, PowerShell parser и исключения для data/build/output. Поиск распространённых token/private-key patterns совпадений не дал (это не исчерпывающий security audit).
- Используется уже настроенный Git author; глобальные Git настройки не менялись. Runtime/рабочие данные не изменялись и сервис не перезапускался.


## Системные CA и Git Bash (28.10.2026)
- Confluence REST/вложения и OpenAI-совместимые API используют общий SSLContext: системное доверие плюс необязательный PEM-файл ARCH_REGISTRY_CA_BUNDLE. Проверка цепочки и hostname обязательна, некорректный файл блокирует запуск.
- PowerShell start.ps1 получил -CaBundle; добавлены Git Bash setup.sh, start.sh и setup-python-runner.sh с преобразованием путей. README содержит команды и ограничения (Windows/Git Bash, не WSL; сертификаты подключаются при запуске, без UI).
- Проверены синтаксис PowerShell/Bash, --help, реальный Git Bash запуск на 8777 с PEM и каталогом с пробелами: HTTP200. Только временная база output/gitbash smoke data; тестовый процесс остановлен. Рабочий процесс 8765 не перезапускался, для применения изменений нужен перезапуск.
- Проверки TLS: обязательная верификация, дополнительный CA без замены системного контекста, настоящий PEM, отказ для отсутствующего/повреждённого файла, явный SSLContext в обоих клиентах. Корпоративные подключения с реальными CA не проверены.


## Script Engine / Node.js Worker (28.10.2026, 0.7.0)
- Новый шаг javascript: код, params, emit, warnings, toMarkdown и saveMarkdown. Node 22 Worker в отдельном ограниченном Docker-контейнере, без локального fallback. Образ закрепляется по ID независимо от Python. npm lock фиксирует Turndown/GFM.
- HTML/Confluence передают очищенный нормализованный HTML; старые снимки дополняются из сохранённого blob без изменения блоков/доказательств. PPTX поддерживается через blocks, без document.html.
- Редактор и JSON шагов поддерживают Script Engine. Отчёт и форма проверки показывают результаты JS, текст Markdown и скачивание .md. Схема, block IDs, конфликт/overwrite и ручное подтверждение сохранены.
- Полный suite с RUN_DOCKER_TESTS=1: 129 passed, включая 9 реальных JS runtime checks и прежние Python isolation checks; одна существующая deprecation warning. Проверены таймаут бесконечного цикла, ошибки, недопустимые пути/размер файлов, схема/источники, изоляция сети/ФС, публикация/закрепление образа. Browser QA: редактор, исполнение, download page.md, публикация, review; мобильная ширина390 без overflow. Только временная output/js-browser. Первый многострочный CLI-вызов имел ошибку передачи синтаксиса; отдельные команды прошли.
- TypeScript/Vite build успешен; PowerShell/Bash setup scripts прошли проверку синтаксиса. Образ architecture-registry-javascript:1 собран.
- Перед запуском 8765 был свободен. Офлайн-backup: output/release-backup-07-20261028-214848. Рабочая0.7.0 запущена: HTTP200, новый bundle, JS runtime available. Все существующие таблицы совпали с backup (исключая TTL llm_outputs). QA остановлен; рабочий8765 оставлен. Корпоративный Confluence не вызывался.
- Инструкция: docs/javascript-engine.md. Коммит/push в этой итерации не выполнялись.


## HTML-снимки Confluence (28.10.2026, 0.7.1)
- REST expand=body.view,version вместо body.storage; HTML обёрнут в UTF-8 документ с title/base и сохраняется с расширением .html. Новые документы format=confluence_html, source_metadata.format=html, config.pipeline_version=confluence-html-v1. Старые XML-снимки читаются прежним парсером, без переписывания доказательств.
- Review предлагает «Скачать HTML» для новых снимков и «Скачать Storage XML» только для прежних. Script Engine получает очищенный HTML. Не возвращаемся к XML при отсутствии body.view.
- 117 тестов прошли, 15 opt-in Docker-тестов пропущены. Проверены запрос body.view, сохранённые HTML/метаданные/скачивание, извлечение полей, безопасный заголовок, отсутствие XML fallback, повторы и пайплайны. TypeScript/Vite build успешен. Реальный корпоративный Confluence не проверялся.
- Backup output/release-backup-071-20261028-220632; рабочий8765 обновлён0.7.1, HTTP200 и bundle проверены. Все существующие таблицы совпали с backup (кроме TTL llm_outputs). Коммит/push не выполнялись.


## Компактный интерфейс и оранжево-синяя палитра (28.10.2026)
- Общие токены: тёмно-оранжевые действия, синие ссылки и навигация, светлый нейтральный фон. Сохранены отдельные цвета успеха/ошибок и видимый keyboard focus.
- Уменьшены отступы панелей24→16px, шагов20→12px, строк таблиц, форм, верхней панели и боковой навигации. На мобильных кнопки не ниже38px. Длинные редакторы ограничены по высоте и прокручиваются.
- TypeScript/Vite build успешен; браузерная проверка пайплайна1280/390 без горизонтального overflow, screenshots output/playwright/design-*.png. Проверено скачивание live CSS с новой палитрой HTTP200. Статическая сборка установлена с резервной копией frontend/dist в output/design-dist-backup-*; backend и пользовательские данные не изменялись.


## PPTX-вложения по CQL (28.10.2026, 0.8.0)
- В Confluence добавлен source_mode=attachments. Сохраняемая очередь проверяет списки вложений страниц с пагинацией и добавляет независимые элементы PPTX; новые источники attachment:<id> не привязываются к объекту страницы. Текущая версия читается перед скачиванием, download закреплён за номером версии. Прежние ручные связи сохраняются.
- Отдельные результаты вложений, страницы без PPTX, отмена, восстановление lease и повтор только failed items. Лимит2500 суммарных этапов; API по умолчанию сохраняет прежний режим HTML pages.
- Проверен сценарий: три PPTX одной страницы, ещё одна без PPTX, пагинация, повтор pending/accepted, переименование+версия2 с прежними object IDs, принятие обновлений до ревизии2, частичная ошибка и retry только файла. 118 passed/15 opt-in Docker skipped; усиленный тест принятия обновлений отдельно passed. TypeScript/Vite build успешен.
- Browser QA только output/attachment-browser: CQL→режимPPTX→3предложения→review. На390px overflow отсутствует. Реальный корпоративный Confluence не вызывался.
- Backup output/release-backup-08-20261028-223125; рабочий8765 обновлён0.8.0, HTTP200/new bundle и сравнение существующих таблиц с backup успешны (кроме TTL llm_outputs). Инструкция docs/confluence-pptx-bulk.md. Коммит/push не выполнялись.
