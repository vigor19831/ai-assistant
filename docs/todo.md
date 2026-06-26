==============================================================================
ПРОМПТ ДЛЯ ЗАПРОСА БАГОВ:
==============================================================================
Ты — архитектор на 30 лет. Найди проблемы, которые сломают проект через 5+ лет, каждый пункт независимый — одна строка, понятен без контекста. Формат вывода:[ ] Название | Последствие | Файл | Проверка |.

==============================================================================
## TODO ##
=============================================================================
Задача 1: Graceful shutdown crash — storage и chunker не IClosable
Проблема: lifespan.py вызывает adapter.shutdown() на всех адаптерах, но SQLiteStorage (IChatStorage) и SimpleChunker (IChunker) не наследуют IClosable. При реальном shutdown — AttributeError.
Что делать: Добавить IClosable в IChatStorage и IChunker, реализовать shutdown() в адаптерах, обновить тесты.

Задача 2: Typed RAGState._status — ReindexStatusEntry dataclass
Проблема: RAGState._status: dict[str, dict[str, object]] — нетипизированный object внутри (drift #14).
Что делать: Создать ReindexStatusEntry dataclass в core/domain/, типизировать RAGState, обновить методы, обновить тесты. JSON API остаётся dict для совместимости.

Задача 3: ChatManager всё ещё использует deprecated async_count_tokens
Проблема: drift #20 заявлен как fixed, но features/chat/manager.py:202 вызывает async_count_tokens вместо self.tokenizer.count(). 40 deprecation warnings в тестах.
Что делать: Заменить вызов на asyncio.to_thread(self.tokenizer.count, ...), убедиться что tokenizer всегда передаётся в PipelineData.

Задача 4: Input validation — пустой messages в OpenAI endpoint
Проблема: OAIChatCompletionRequest не валидирует messages на минимальную длину. OpenAI-compatible endpoint принимает {"messages": []} и падает с 500 вместо 422.
Что делать: Добавить Pydantic validator в OAIChatCompletionRequest на len(messages) >= 1.

Задача 5: Проверить auto-save индексов
Проблема: Нет — нужно убедиться что текущая реализация достаточна.
Что делать: Аудит lifespan.py — сохраняются ли индексы при SIGTERM/SIGINT, есть ли race condition при одновременном save() и add(), нужен ли периодический auto-save (не только при shutdown).

Задача 6: Проверить graceful degradation при недоступном LLM
Проблема: Нет — нужно убедиться что текущая реализация работает.
Что делать: Проверить таймауты, retry, fallback сообщения. Убедиться что AdapterError мапится в 503, а не 500. Проверить что streaming endpoint тоже возвращает понятную ошибку, а не обрывает соединение.
