| table_name          | column_name                 | data_type                | is_nullable | column_default               |
| ------------------- | --------------------------- | ------------------------ | ----------- | ---------------------------- |
| api_keys            | id                          | uuid                     | NO          | gen_random_uuid()            |
| api_keys            | user_id                     | uuid                     | NO          | null                         |
| api_keys            | name                        | text                     | NO          | null                         |
| api_keys            | prefix                      | text                     | NO          | null                         |
| api_keys            | key_hash                    | text                     | NO          | null                         |
| api_keys            | scopes                      | ARRAY                    | NO          | '{}'::text[]                 |
| api_keys            | expires_at                  | timestamp with time zone | YES         | null                         |
| api_keys            | revoked_at                  | timestamp with time zone | YES         | null                         |
| api_keys            | last_used_at                | timestamp with time zone | YES         | null                         |
| api_keys            | created_at                  | timestamp with time zone | NO          | now()                        |
| asset_derivatives   | parent_asset_id             | uuid                     | NO          | null                         |
| asset_derivatives   | child_asset_id              | uuid                     | NO          | null                         |
| asset_derivatives   | relation                    | text                     | NO          | null                         |
| assets              | id                          | uuid                     | NO          | gen_random_uuid()            |
| assets              | user_id                     | uuid                     | NO          | null                         |
| assets              | type                        | text                     | NO          | null                         |
| assets              | bucket                      | text                     | NO          | 'assets'::text               |
| assets              | path                        | text                     | NO          | null                         |
| assets              | filename                    | text                     | NO          | null                         |
| assets              | mime_type                   | text                     | YES         | null                         |
| assets              | size_bytes                  | bigint                   | YES         | null                         |
| assets              | width                       | integer                  | YES         | null                         |
| assets              | height                      | integer                  | YES         | null                         |
| assets              | duration_seconds            | numeric                  | YES         | null                         |
| assets              | folder_id                   | uuid                     | YES         | null                         |
| assets              | source_task_id              | uuid                     | YES         | null                         |
| assets              | checksum                    | text                     | YES         | null                         |
| assets              | metadata                    | jsonb                    | NO          | '{}'::jsonb                  |
| assets              | status                      | text                     | NO          | 'ready'::text                |
| assets              | created_at                  | timestamp with time zone | NO          | now()                        |
| credit_transactions | id                          | uuid                     | NO          | gen_random_uuid()            |
| credit_transactions | user_id                     | uuid                     | NO          | null                         |
| credit_transactions | amount                      | integer                  | NO          | null                         |
| credit_transactions | transaction_type            | text                     | NO          | null                         |
| credit_transactions | description                 | text                     | YES         | null                         |
| credit_transactions | subscription_id             | uuid                     | YES         | null                         |
| credit_transactions | metadata                    | jsonb                    | YES         | '{}'::jsonb                  |
| credit_transactions | created_at                  | timestamp with time zone | NO          | now()                        |
| folder_tree         | id                          | uuid                     | YES         | null                         |
| folder_tree         | user_id                     | uuid                     | YES         | null                         |
| folder_tree         | name                        | text                     | YES         | null                         |
| folder_tree         | parent_id                   | uuid                     | YES         | null                         |
| folder_tree         | path                        | USER-DEFINED             | YES         | null                         |
| folder_tree         | full_path                   | text                     | YES         | null                         |
| folders             | id                          | uuid                     | NO          | gen_random_uuid()            |
| folders             | user_id                     | uuid                     | NO          | null                         |
| folders             | name                        | text                     | NO          | null                         |
| folders             | parent_id                   | uuid                     | YES         | null                         |
| folders             | path                        | USER-DEFINED             | NO          | null                         |
| folders             | created_at                  | timestamp with time zone | NO          | now()                        |
| models              | id                          | uuid                     | NO          | gen_random_uuid()            |
| models              | provider                    | text                     | NO          | null                         |
| models              | name                        | text                     | NO          | null                         |
| models              | version                     | text                     | YES         | null                         |
| models              | supports_operation          | uuid                     | NO          | null                         |
| models              | input_schema                | jsonb                    | NO          | '{}'::jsonb                  |
| models              | output_type                 | text                     | NO          | 'asset'::text                |
| models              | metadata                    | jsonb                    | NO          | '{}'::jsonb                  |
| models              | is_active                   | boolean                  | NO          | true                         |
| models              | created_at                  | timestamp with time zone | NO          | now()                        |
| operations          | id                          | uuid                     | NO          | gen_random_uuid()            |
| operations          | key                         | text                     | NO          | null                         |
| operations          | label                       | text                     | NO          | null                         |
| operations          | description                 | text                     | YES         | null                         |
| operations          | created_at                  | timestamp with time zone | NO          | now()                        |
| replicate_jobs      | id                          | uuid                     | NO          | gen_random_uuid()            |
| replicate_jobs      | user_id                     | uuid                     | YES         | null                         |
| replicate_jobs      | prediction_id               | text                     | NO          | null                         |
| replicate_jobs      | model                       | text                     | NO          | null                         |
| replicate_jobs      | prompt                      | text                     | YES         | null                         |
| replicate_jobs      | status                      | text                     | NO          | 'queued'::text               |
| replicate_jobs      | output                      | jsonb                    | YES         | null                         |
| replicate_jobs      | metadata                    | jsonb                    | NO          | '{}'::jsonb                  |
| replicate_jobs      | error_message               | text                     | YES         | null                         |
| replicate_jobs      | credits_spent               | integer                  | YES         | null                         |
| replicate_jobs      | created_at                  | timestamp with time zone | NO          | timezone('utc'::text, now()) |
| replicate_jobs      | completed_at                | timestamp with time zone | YES         | null                         |
| replicate_jobs      | updated_at                  | timestamp with time zone | NO          | timezone('utc'::text, now()) |
| subscriptions       | id                          | uuid                     | NO          | gen_random_uuid()            |
| subscriptions       | user_id                     | uuid                     | YES         | null                         |
| subscriptions       | stripe_customer_id          | text                     | YES         | null                         |
| subscriptions       | stripe_subscription_id      | text                     | YES         | null                         |
| subscriptions       | status                      | text                     | YES         | null                         |
| subscriptions       | price_id                    | text                     | YES         | null                         |
| subscriptions       | created_at                  | timestamp with time zone | YES         | now()                        |
| subscriptions       | cancel_at_period_end        | boolean                  | YES         | false                        |
| subscriptions       | updated_at                  | timestamp with time zone | YES         | now()                        |
| subscriptions       | current_period_end          | timestamp with time zone | YES         | null                         |
| subscriptions       | plan_id                     | text                     | YES         | null                         |
| tasks               | id                          | uuid                     | NO          | gen_random_uuid()            |
| tasks               | user_id                     | uuid                     | NO          | null                         |
| tasks               | operation_id                | uuid                     | NO          | null                         |
| tasks               | model_id                    | uuid                     | NO          | null                         |
| tasks               | external_prediction_id      | text                     | YES         | null                         |
| tasks               | status                      | text                     | NO          | 'queued'::text               |
| tasks               | input                       | jsonb                    | NO          | '{}'::jsonb                  |
| tasks               | metadata                    | jsonb                    | NO          | '{}'::jsonb                  |
| tasks               | error_message               | text                     | YES         | null                         |
| tasks               | credits_spent               | integer                  | YES         | null                         |
| tasks               | created_at                  | timestamp with time zone | NO          | timezone('utc'::text, now()) |
| tasks               | updated_at                  | timestamp with time zone | NO          | timezone('utc'::text, now()) |
| tasks               | completed_at                | timestamp with time zone | YES         | null                         |
| temp_uploads        | id                          | uuid                     | NO          | gen_random_uuid()            |
| temp_uploads        | user_id                     | uuid                     | NO          | null                         |
| temp_uploads        | bucket                      | text                     | NO          | 'temp'::text                 |
| temp_uploads        | path                        | text                     | NO          | null                         |
| temp_uploads        | filename                    | text                     | NO          | null                         |
| temp_uploads        | mime_type                   | text                     | YES         | null                         |
| temp_uploads        | size_bytes                  | bigint                   | YES         | null                         |
| temp_uploads        | task_id                     | uuid                     | YES         | null                         |
| temp_uploads        | expires_at                  | timestamp with time zone | NO          | null                         |
| temp_uploads        | signed_until                | timestamp with time zone | YES         | null                         |
| temp_uploads        | metadata                    | jsonb                    | NO          | '{}'::jsonb                  |
| temp_uploads        | created_at                  | timestamp with time zone | NO          | now()                        |
| user_credits        | id                          | uuid                     | NO          | gen_random_uuid()            |
| user_credits        | user_id                     | uuid                     | NO          | null                         |
| user_credits        | total_credits               | integer                  | NO          | 0                            |
| user_credits        | used_credits                | integer                  | NO          | 0                            |
| user_credits        | available_credits           | integer                  | YES         | null                         |
| user_credits        | created_at                  | timestamp with time zone | NO          | now()                        |
| user_credits        | updated_at                  | timestamp with time zone | NO          | now()                        |
| user_preferences    | id                          | uuid                     | NO          | uuid_generate_v4()           |
| user_preferences    | user_id                     | uuid                     | NO          | null                         |
| user_preferences    | has_completed_onboarding    | boolean                  | YES         | false                        |
| user_preferences    | created_at                  | timestamp with time zone | NO          | timezone('utc'::text, now()) |
| user_preferences    | updated_at                  | timestamp with time zone | NO          | timezone('utc'::text, now()) |
| user_trials         | id                          | uuid                     | NO          | uuid_generate_v4()           |
| user_trials         | user_id                     | uuid                     | NO          | null                         |
| user_trials         | trial_start_time            | timestamp with time zone | YES         | now()                        |
| user_trials         | trial_end_time              | timestamp with time zone | NO          | null                         |
| user_trials         | is_trial_used               | boolean                  | YES         | false                        |
| users               | id                          | uuid                     | NO          | null                         |
| users               | instance_id                 | uuid                     | YES         | null                         |
| users               | email                       | text                     | YES         | null                         |
| users               | id                          | uuid                     | NO          | null                         |
| users               | aud                         | character varying        | YES         | null                         |
| users               | created_at                  | timestamp with time zone | NO          | timezone('utc'::text, now()) |
| users               | updated_at                  | timestamp with time zone | NO          | timezone('utc'::text, now()) |
| users               | role                        | character varying        | YES         | null                         |
| users               | email                       | character varying        | YES         | null                         |
| users               | is_deleted                  | boolean                  | YES         | false                        |
| users               | encrypted_password          | character varying        | YES         | null                         |
| users               | deleted_at                  | timestamp with time zone | YES         | null                         |
| users               | reactivated_at              | timestamp with time zone | YES         | null                         |
| users               | email_confirmed_at          | timestamp with time zone | YES         | null                         |
| users               | invited_at                  | timestamp with time zone | YES         | null                         |
| users               | confirmation_token          | character varying        | YES         | null                         |
| users               | confirmation_sent_at        | timestamp with time zone | YES         | null                         |
| users               | recovery_token              | character varying        | YES         | null                         |
| users               | recovery_sent_at            | timestamp with time zone | YES         | null                         |
| users               | email_change_token_new      | character varying        | YES         | null                         |
| users               | email_change                | character varying        | YES         | null                         |
| users               | email_change_sent_at        | timestamp with time zone | YES         | null                         |
| users               | last_sign_in_at             | timestamp with time zone | YES         | null                         |
| users               | raw_app_meta_data           | jsonb                    | YES         | null                         |
| users               | raw_user_meta_data          | jsonb                    | YES         | null                         |
| users               | is_super_admin              | boolean                  | YES         | null                         |
| users               | created_at                  | timestamp with time zone | YES         | null                         |
| users               | updated_at                  | timestamp with time zone | YES         | null                         |
| users               | phone                       | text                     | YES         | NULL::character varying      |
| users               | phone_confirmed_at          | timestamp with time zone | YES         | null                         |
| users               | phone_change                | text                     | YES         | ''::character varying        |
| users               | phone_change_token          | character varying        | YES         | ''::character varying        |
| users               | phone_change_sent_at        | timestamp with time zone | YES         | null                         |
| users               | confirmed_at                | timestamp with time zone | YES         | null                         |
| users               | email_change_token_current  | character varying        | YES         | ''::character varying        |
| users               | email_change_confirm_status | smallint                 | YES         | 0                            |
| users               | banned_until                | timestamp with time zone | YES         | null                         |
| users               | reauthentication_token      | character varying        | YES         | ''::character varying        |
| users               | reauthentication_sent_at    | timestamp with time zone | YES         | null                         |
| users               | is_sso_user                 | boolean                  | NO          | false                        |
| users               | deleted_at                  | timestamp with time zone | YES         | null                         |
| users               | is_anonymous                | boolean                  | NO          | false                        |