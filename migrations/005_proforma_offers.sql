-- Migration 005: proforma_offers tablosu (GAP-2)
-- Supabase SQL Editor'da çalıştır: https://supabase.com/dashboard/project/ypusjrrklxssjvefkypd/sql
-- Tarih: 21 Temmuz 2026

CREATE TABLE IF NOT EXISTS proforma_offers (
  id                        uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  product_id                uuid REFERENCES products(id),
  supplier_contact_id       uuid REFERENCES supplier_contacts(id),
  teklif_fiyat_usd          numeric,
  moq                       integer,
  teslim_sure_gun           integer,
  tahmini_cogs_tl           numeric,
  tahmini_marj_pct          numeric,
  firsatci_tahmini_fark_tl  numeric,
  status                    text DEFAULT 'pending',  -- pending/approved/rejected
  note                      text,
  mock                      boolean DEFAULT false,
  created_at                timestamptz DEFAULT now(),
  reviewed_at               timestamptz
);

ALTER TABLE proforma_offers ENABLE ROW LEVEL SECURITY;

CREATE INDEX IF NOT EXISTS idx_proforma_offers_product
  ON proforma_offers (product_id);

CREATE INDEX IF NOT EXISTS idx_proforma_offers_supplier_contact
  ON proforma_offers (supplier_contact_id);

CREATE INDEX IF NOT EXISTS idx_proforma_offers_status
  ON proforma_offers (status);
