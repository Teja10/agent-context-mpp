ALTER TABLE one_time_purchases
    ADD COLUMN recipient_wallet TEXT NOT NULL CHECK (recipient_wallet <> '');
