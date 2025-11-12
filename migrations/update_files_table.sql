-- Миграция для расширения таблицы files
-- Добавляет поля для хранения метаданных анализа PDF
-- Все данные анализа хранятся в analysis_json, отдельное поле reading_time_min только для индексации

-- Добавляем новые поля
ALTER TABLE files 
  ADD COLUMN IF NOT EXISTS telegram_file_id TEXT,
  ADD COLUMN IF NOT EXISTS source_url TEXT,
  ADD COLUMN IF NOT EXISTS title TEXT,
  ADD COLUMN IF NOT EXISTS reading_time_min NUMERIC,
  ADD COLUMN IF NOT EXISTS analysis_json JSONB,
  ADD COLUMN IF NOT EXISTS created_at TIMESTAMP DEFAULT NOW();

-- Создаём индексы для быстрого поиска
CREATE INDEX IF NOT EXISTS idx_files_reading_time ON files(reading_time_min);
CREATE INDEX IF NOT EXISTS idx_files_user_reading_time ON files(user_id, reading_time_min);
CREATE INDEX IF NOT EXISTS idx_files_analysis_json ON files USING GIN(analysis_json);

-- Примечание: 
-- - reading_time_min вынесено в отдельное поле для производительности алгоритма подбора
-- - Все остальные данные (complexity, topics, category, volume) хранятся в analysis_json
-- - GIN-индекс на analysis_json позволяет эффективно искать по тегам и категориям через JSONB-запросы

