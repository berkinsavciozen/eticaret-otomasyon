-- Migration 002: approval_queue M4 kolonları
-- Supabase SQL Editor'da çalıştır: https://supabase.com/dashboard/project/ypusjrrklxssjvefkypd/sql
-- Tarih: 2024 M4

-- 1. metadata JSONB: deterministik puanlama skoru + priority + sermaye_ok
ALTER TABLE approval_queue
  ADD COLUMN IF NOT EXISTS metadata JSONB;

-- 2. category TEXT: Trendyol kategori yolu (e.g. "Elektronik > Kulaklıklar")
ALTER TABLE approval_queue
  ADD COLUMN IF NOT EXISTS category TEXT;

-- 3. updated_at: yeniden skorlama zaman damgası
ALTER TABLE approval_queue
  ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ DEFAULT NOW();

-- 4. estimated_price_tl INT: tahmini satış fiyatı (Sheets mirror için)
ALTER TABLE approval_queue
  ADD COLUMN IF NOT EXISTS estimated_price_tl INTEGER;

-- Index: metadata üzerinde GIN index (JSONB sorguları için)
CREATE INDEX IF NOT EXISTS idx_approval_queue_metadata
  ON approval_queue USING GIN (metadata);

-- Index: agent_source + status birleşik sorgu için
CREATE INDEX IF NOT EXISTS idx_approval_queue_agent_status
  ON approval_queue (agent_source, status);
