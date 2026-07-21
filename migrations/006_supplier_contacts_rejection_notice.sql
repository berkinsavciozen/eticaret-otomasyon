-- Migration 006: supplier_contacts.rejection_notice_drafted (GAP-9)
-- Supabase SQL Editor'da çalıştır: https://supabase.com/dashboard/project/ypusjrrklxssjvefkypd/sql
-- Tarih: 21 Temmuz 2026

-- Tedarikçi RED'inde onaya tabi red bildirimi maili taslağı bir kez
-- üretilsin diye (duplicate önleme).
ALTER TABLE supplier_contacts
  ADD COLUMN IF NOT EXISTS rejection_notice_drafted BOOLEAN DEFAULT FALSE;
