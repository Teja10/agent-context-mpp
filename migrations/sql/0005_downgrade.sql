DROP TABLE subscription_renewal_attempts;
DROP TABLE subscription_authorization_keys;
DROP INDEX subscription_authorizations_one_active;
DROP TABLE subscription_authorizations;

ALTER TABLE subscriptions
    ALTER COLUMN period_start TYPE DATE USING period_start::date,
    ALTER COLUMN period_end TYPE DATE USING period_end::date;
