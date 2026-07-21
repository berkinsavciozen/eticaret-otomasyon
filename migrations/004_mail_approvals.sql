-- Migration 004: mail_approvals tablosu (GAP-1)
-- Supabase SQL Editor'da çalıştır: https://supabase.com/dashboard/project/ypusjrrklxssjvefkypd/sql
-- Tarih: 21 Temmuz 2026

CREATE TABLE IF NOT EXISTS mail_approvals (
  id                    uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tm_id                 text UNIQUE NOT NULL,
  product_id            uuid REFERENCES products(id),
  supplier_contact_id   uuid REFERENCES supplier_contacts(id),
  mail_turu             text DEFAULT 'ilk_temas',
  email_body            text,
  test_gonderildi_at    timestamptz,
  excel_onay            text,
  gmail_yaniti_alindi   boolean DEFAULT false,
  onay_durumu           text DEFAULT 'pending',
  gercek_gonderim_at    timestamptz,
  note                  text,
  created_at            timestamptz DEFAULT now()
);

ALTER TABLE mail_approvals ENABLE ROW LEVEL SECURITY;

CREATE INDEX IF NOT EXISTS idx_mail_approvals_tm_id
  ON mail_approvals (tm_id);

CREATE INDEX IF NOT EXISTS idx_mail_approvals_supplier_contact
  ON mail_approvals (supplier_contact_id);

CREATE INDEX IF NOT EXISTS idx_mail_approvals_onay_durumu
  ON mail_approvals (onay_durumu);
