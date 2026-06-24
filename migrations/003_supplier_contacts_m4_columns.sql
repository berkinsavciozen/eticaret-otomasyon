-- Migration 003: supplier_contacts M4 kolonları
-- Supabase SQL Editor'da çalıştır: https://supabase.com/dashboard/project/ypusjrrklxssjvefkypd/sql
-- Tarih: 2024 M4

-- 1. tm_id: Test mail TM-001 formatı (sadece test mail konusunda, tedarikçi mailinde YOK)
ALTER TABLE supplier_contacts
  ADD COLUMN IF NOT EXISTS tm_id TEXT;

-- 2. iliski_tipi: new / known_new_product / reorder
ALTER TABLE supplier_contacts
  ADD COLUMN IF NOT EXISTS iliski_tipi TEXT DEFAULT 'new';

-- 3. url: Tedarikçi Alibaba/1688 URL
ALTER TABLE supplier_contacts
  ADD COLUMN IF NOT EXISTS url TEXT;

-- 4. birim_usd: Tahmini birim fiyat (USD)
ALTER TABLE supplier_contacts
  ADD COLUMN IF NOT EXISTS birim_usd NUMERIC;

-- 5. moq: Minimum sipariş miktarı
ALTER TABLE supplier_contacts
  ADD COLUMN IF NOT EXISTS moq INTEGER;

-- 6. supplier_scoring: Puanlama detayı JSONB
ALTER TABLE supplier_contacts
  ADD COLUMN IF NOT EXISTS supplier_scoring JSONB;

-- 7. mock: Mock tedarikçi flag'i (gerçek mail gönderilmez)
ALTER TABLE supplier_contacts
  ADD COLUMN IF NOT EXISTS mock BOOLEAN DEFAULT FALSE;

-- Index: tm_id sorgusu için
CREATE INDEX IF NOT EXISTS idx_supplier_contacts_tm_id
  ON supplier_contacts (tm_id) WHERE tm_id IS NOT NULL;

-- Index: product_id + status
CREATE INDEX IF NOT EXISTS idx_supplier_contacts_product_status
  ON supplier_contacts (product_id, status);
