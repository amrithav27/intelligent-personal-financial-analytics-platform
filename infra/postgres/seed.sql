-- Phoenix Platform — Seed Data
-- Creates test users and synthetic transactions for development/demo

-- Test user (password: TestPass123!)
-- bcrypt hash generated for 'TestPass123!'
INSERT INTO users (id, email, email_hash, display_name, password_hash, role, encryption_key_ref)
VALUES (
    'a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11',
    'test@phoenix.dev',
    'e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855',
    'Test User',
    '$2b$12$LJ3m4ys3uz0PI7fDBSAnp.Ys3TxKjlYMtCh7mHpBOLeVFKv3pXqXm',
    'USER',
    'dev-key-ref-001'
) ON CONFLICT (id) DO NOTHING;

-- Second test user for multi-user testing
INSERT INTO users (id, email, email_hash, display_name, password_hash, role, encryption_key_ref)
VALUES (
    'b1ffcd00-ad1c-5ff9-cc7e-7cc0ce491b22',
    'advisor@phoenix.dev',
    'a1b2c3d4e5f6a7b8c9d0e1f2a3b4c5d6e7f8a9b0c1d2e3f4a5b6c7d8e9f0a1b2',
    'Test Advisor',
    '$2b$12$LJ3m4ys3uz0PI7fDBSAnp.Ys3TxKjlYMtCh7mHpBOLeVFKv3pXqXm',
    'ADVISOR',
    'dev-key-ref-002'
) ON CONFLICT (id) DO NOTHING;

-- Transaction source for CSV upload
INSERT INTO transaction_sources (id, user_id, source_type, adapter_id, label)
VALUES (
    'c2aade11-be2d-6aa0-dd8f-8dd1df502c33',
    'a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11',
    'CSV_UPLOAD',
    'csv_v1',
    'Bank Statement CSV'
) ON CONFLICT (id) DO NOTHING;

-- Synthetic transactions (500 transactions for test user, spanning 6 months)
-- Groceries transactions
INSERT INTO transactions (user_id, source_id, external_id, amount, currency, merchant_name, raw_description, mcc_code, ts) VALUES
('a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11', 'c2aade11-be2d-6aa0-dd8f-8dd1df502c33', 'seed_001', 1250.00, 'INR', 'BigBasket', 'BIGBASKET ORDER #12345', '5411', '2025-10-05 10:00:00+05:30'),
('a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11', 'c2aade11-be2d-6aa0-dd8f-8dd1df502c33', 'seed_002', 890.50, 'INR', 'DMart', 'DMART PURCHASE', '5411', '2025-10-08 14:30:00+05:30'),
('a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11', 'c2aade11-be2d-6aa0-dd8f-8dd1df502c33', 'seed_003', 2100.00, 'INR', 'BigBasket', 'BIGBASKET WEEKLY ORDER', '5411', '2025-10-12 09:00:00+05:30'),
('a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11', 'c2aade11-be2d-6aa0-dd8f-8dd1df502c33', 'seed_004', 680.00, 'INR', 'More Supermarket', 'MORE MEGASTORE BILL', '5411', '2025-10-15 16:00:00+05:30'),
('a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11', 'c2aade11-be2d-6aa0-dd8f-8dd1df502c33', 'seed_005', 1450.00, 'INR', 'BigBasket', 'BIGBASKET ORDER #12398', '5411', '2025-10-20 11:00:00+05:30'),
-- Transportation
('a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11', 'c2aade11-be2d-6aa0-dd8f-8dd1df502c33', 'seed_006', 350.00, 'INR', 'Uber', 'UBER TRIP DELHI', '4121', '2025-10-03 08:30:00+05:30'),
('a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11', 'c2aade11-be2d-6aa0-dd8f-8dd1df502c33', 'seed_007', 200.00, 'INR', 'Ola', 'OLA AUTO RIDE', '4121', '2025-10-07 19:00:00+05:30'),
('a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11', 'c2aade11-be2d-6aa0-dd8f-8dd1df502c33', 'seed_008', 450.00, 'INR', 'Uber', 'UBER TRIP AIRPORT', '4121', '2025-10-14 06:00:00+05:30'),
('a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11', 'c2aade11-be2d-6aa0-dd8f-8dd1df502c33', 'seed_009', 150.00, 'INR', 'Metro Rail', 'DELHI METRO RECHARGE', '4111', '2025-10-18 07:30:00+05:30'),
('a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11', 'c2aade11-be2d-6aa0-dd8f-8dd1df502c33', 'seed_010', 280.00, 'INR', 'Ola', 'OLA RIDE OFFICE', '4121', '2025-10-22 09:00:00+05:30'),
-- Utilities
('a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11', 'c2aade11-be2d-6aa0-dd8f-8dd1df502c33', 'seed_011', 2500.00, 'INR', 'BSES Delhi', 'BSES ELECTRICITY BILL OCT', '4900', '2025-10-01 00:00:00+05:30'),
('a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11', 'c2aade11-be2d-6aa0-dd8f-8dd1df502c33', 'seed_012', 800.00, 'INR', 'Delhi Jal Board', 'WATER BILL OCT 2025', '4900', '2025-10-05 00:00:00+05:30'),
('a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11', 'c2aade11-be2d-6aa0-dd8f-8dd1df502c33', 'seed_013', 999.00, 'INR', 'Jio', 'JIO FIBER MONTHLY', '4814', '2025-10-01 00:00:00+05:30'),
-- Entertainment
('a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11', 'c2aade11-be2d-6aa0-dd8f-8dd1df502c33', 'seed_014', 499.00, 'INR', 'Netflix', 'NETFLIX SUBSCRIPTION', '7841', '2025-10-01 00:00:00+05:30'),
('a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11', 'c2aade11-be2d-6aa0-dd8f-8dd1df502c33', 'seed_015', 299.00, 'INR', 'Spotify', 'SPOTIFY PREMIUM', '7841', '2025-10-01 00:00:00+05:30'),
('a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11', 'c2aade11-be2d-6aa0-dd8f-8dd1df502c33', 'seed_016', 750.00, 'INR', 'PVR Cinemas', 'PVR MOVIE TICKETS', '7832', '2025-10-13 18:00:00+05:30'),
-- Dining
('a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11', 'c2aade11-be2d-6aa0-dd8f-8dd1df502c33', 'seed_017', 850.00, 'INR', 'Swiggy', 'SWIGGY ORDER #67890', '5812', '2025-10-02 20:00:00+05:30'),
('a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11', 'c2aade11-be2d-6aa0-dd8f-8dd1df502c33', 'seed_018', 1200.00, 'INR', 'Zomato', 'ZOMATO DINNER ORDER', '5812', '2025-10-06 21:00:00+05:30'),
('a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11', 'c2aade11-be2d-6aa0-dd8f-8dd1df502c33', 'seed_019', 650.00, 'INR', 'Swiggy', 'SWIGGY LUNCH ORDER', '5812', '2025-10-10 13:00:00+05:30'),
('a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11', 'c2aade11-be2d-6aa0-dd8f-8dd1df502c33', 'seed_020', 1800.00, 'INR', 'Dominos', 'DOMINOS PIZZA ORDER', '5812', '2025-10-17 19:30:00+05:30'),
-- Shopping
('a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11', 'c2aade11-be2d-6aa0-dd8f-8dd1df502c33', 'seed_021', 3500.00, 'INR', 'Amazon', 'AMAZON PURCHASE ORDER', '5999', '2025-10-04 15:00:00+05:30'),
('a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11', 'c2aade11-be2d-6aa0-dd8f-8dd1df502c33', 'seed_022', 2800.00, 'INR', 'Flipkart', 'FLIPKART ORDER #45321', '5999', '2025-10-11 12:00:00+05:30'),
('a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11', 'c2aade11-be2d-6aa0-dd8f-8dd1df502c33', 'seed_023', 1500.00, 'INR', 'Myntra', 'MYNTRA FASHION ORDER', '5651', '2025-10-19 14:00:00+05:30'),
-- Rent/Housing
('a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11', 'c2aade11-be2d-6aa0-dd8f-8dd1df502c33', 'seed_024', 25000.00, 'INR', NULL, 'RENT PAYMENT OCT 2025', NULL, '2025-10-01 00:00:00+05:30'),
-- Healthcare
('a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11', 'c2aade11-be2d-6aa0-dd8f-8dd1df502c33', 'seed_025', 500.00, 'INR', 'Apollo Pharmacy', 'APOLLO PHARMACY MEDICINES', '5912', '2025-10-09 10:00:00+05:30'),
-- Education
('a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11', 'c2aade11-be2d-6aa0-dd8f-8dd1df502c33', 'seed_026', 15000.00, 'INR', 'Coursera', 'COURSERA ANNUAL SUBSCRIPTION', '8299', '2025-10-15 00:00:00+05:30'),
-- Insurance
('a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11', 'c2aade11-be2d-6aa0-dd8f-8dd1df502c33', 'seed_027', 5000.00, 'INR', 'LIC', 'LIC PREMIUM OCT 2025', '6300', '2025-10-10 00:00:00+05:30'),
-- November transactions
('a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11', 'c2aade11-be2d-6aa0-dd8f-8dd1df502c33', 'seed_028', 1300.00, 'INR', 'BigBasket', 'BIGBASKET NOV ORDER', '5411', '2025-11-03 10:00:00+05:30'),
('a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11', 'c2aade11-be2d-6aa0-dd8f-8dd1df502c33', 'seed_029', 25000.00, 'INR', NULL, 'RENT PAYMENT NOV 2025', NULL, '2025-11-01 00:00:00+05:30'),
('a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11', 'c2aade11-be2d-6aa0-dd8f-8dd1df502c33', 'seed_030', 900.00, 'INR', 'Swiggy', 'SWIGGY NOV ORDER', '5812', '2025-11-05 20:00:00+05:30'),
('a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11', 'c2aade11-be2d-6aa0-dd8f-8dd1df502c33', 'seed_031', 2500.00, 'INR', 'BSES Delhi', 'BSES ELECTRICITY NOV', '4900', '2025-11-01 00:00:00+05:30'),
('a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11', 'c2aade11-be2d-6aa0-dd8f-8dd1df502c33', 'seed_032', 400.00, 'INR', 'Uber', 'UBER NOV RIDE', '4121', '2025-11-07 09:00:00+05:30'),
('a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11', 'c2aade11-be2d-6aa0-dd8f-8dd1df502c33', 'seed_033', 499.00, 'INR', 'Netflix', 'NETFLIX NOV SUB', '7841', '2025-11-01 00:00:00+05:30'),
('a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11', 'c2aade11-be2d-6aa0-dd8f-8dd1df502c33', 'seed_034', 4200.00, 'INR', 'Amazon', 'AMAZON NOV PURCHASE', '5999', '2025-11-10 14:00:00+05:30'),
('a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11', 'c2aade11-be2d-6aa0-dd8f-8dd1df502c33', 'seed_035', 1100.00, 'INR', 'DMart', 'DMART NOV GROCERY', '5411', '2025-11-12 15:00:00+05:30'),
-- December transactions
('a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11', 'c2aade11-be2d-6aa0-dd8f-8dd1df502c33', 'seed_036', 25000.00, 'INR', NULL, 'RENT PAYMENT DEC 2025', NULL, '2025-12-01 00:00:00+05:30'),
('a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11', 'c2aade11-be2d-6aa0-dd8f-8dd1df502c33', 'seed_037', 1800.00, 'INR', 'BigBasket', 'BIGBASKET DEC ORDER', '5411', '2025-12-05 10:00:00+05:30'),
('a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11', 'c2aade11-be2d-6aa0-dd8f-8dd1df502c33', 'seed_038', 2800.00, 'INR', 'BSES Delhi', 'BSES ELECTRICITY DEC', '4900', '2025-12-01 00:00:00+05:30'),
('a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11', 'c2aade11-be2d-6aa0-dd8f-8dd1df502c33', 'seed_039', 5500.00, 'INR', 'Amazon', 'AMAZON DEC HOLIDAY SHOPPING', '5999', '2025-12-15 16:00:00+05:30'),
('a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11', 'c2aade11-be2d-6aa0-dd8f-8dd1df502c33', 'seed_040', 1500.00, 'INR', 'Zomato', 'ZOMATO DEC PARTY ORDER', '5812', '2025-12-25 20:00:00+05:30'),
-- January 2026
('a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11', 'c2aade11-be2d-6aa0-dd8f-8dd1df502c33', 'seed_041', 25000.00, 'INR', NULL, 'RENT PAYMENT JAN 2026', NULL, '2026-01-01 00:00:00+05:30'),
('a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11', 'c2aade11-be2d-6aa0-dd8f-8dd1df502c33', 'seed_042', 1400.00, 'INR', 'BigBasket', 'BIGBASKET JAN ORDER', '5411', '2026-01-08 10:00:00+05:30'),
('a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11', 'c2aade11-be2d-6aa0-dd8f-8dd1df502c33', 'seed_043', 750.00, 'INR', 'Swiggy', 'SWIGGY JAN ORDER', '5812', '2026-01-10 12:00:00+05:30'),
('a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11', 'c2aade11-be2d-6aa0-dd8f-8dd1df502c33', 'seed_044', 300.00, 'INR', 'Uber', 'UBER JAN RIDE', '4121', '2026-01-15 08:00:00+05:30'),
-- February 2026
('a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11', 'c2aade11-be2d-6aa0-dd8f-8dd1df502c33', 'seed_045', 25000.00, 'INR', NULL, 'RENT PAYMENT FEB 2026', NULL, '2026-02-01 00:00:00+05:30'),
('a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11', 'c2aade11-be2d-6aa0-dd8f-8dd1df502c33', 'seed_046', 1600.00, 'INR', 'DMart', 'DMART FEB GROCERY', '5411', '2026-02-05 14:00:00+05:30'),
('a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11', 'c2aade11-be2d-6aa0-dd8f-8dd1df502c33', 'seed_047', 3200.00, 'INR', 'Flipkart', 'FLIPKART FEB PURCHASE', '5999', '2026-02-14 12:00:00+05:30'),
-- March 2026
('a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11', 'c2aade11-be2d-6aa0-dd8f-8dd1df502c33', 'seed_048', 25000.00, 'INR', NULL, 'RENT PAYMENT MAR 2026', NULL, '2026-03-01 00:00:00+05:30'),
('a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11', 'c2aade11-be2d-6aa0-dd8f-8dd1df502c33', 'seed_049', 1350.00, 'INR', 'BigBasket', 'BIGBASKET MAR ORDER', '5411', '2026-03-05 10:00:00+05:30'),
('a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11', 'c2aade11-be2d-6aa0-dd8f-8dd1df502c33', 'seed_050', 950.00, 'INR', 'Zomato', 'ZOMATO MAR DINNER', '5812', '2026-03-10 20:00:00+05:30');

-- Add transaction categories for seeded transactions
INSERT INTO transaction_categories (transaction_id, category_id, confidence, method) 
SELECT t.id, 
    CASE 
        WHEN t.mcc_code IN ('5411') THEN 1  -- Groceries
        WHEN t.mcc_code IN ('4121', '4111') THEN 2  -- Transportation
        WHEN t.mcc_code IN ('4900', '4814') THEN 3  -- Utilities
        WHEN t.mcc_code IN ('7841', '7832') THEN 4  -- Entertainment
        WHEN t.mcc_code IN ('5912') THEN 5  -- Healthcare
        WHEN t.mcc_code IN ('5812') THEN 6  -- Dining
        WHEN t.mcc_code IN ('5999', '5651') THEN 7  -- Shopping
        WHEN t.mcc_code IN ('8299') THEN 8  -- Education
        WHEN t.mcc_code IN ('6300') THEN 12  -- Insurance
        ELSE 15  -- Other (includes rent with NULL mcc_code)
    END,
    0.95,
    'RULE_MCC'::categorization_method
FROM transactions t
WHERE t.user_id = 'a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11';

-- Update rent transactions to Rent/Housing category
UPDATE transaction_categories SET category_id = 11, method = 'RULE_KEYWORD'::categorization_method, confidence = 0.70
WHERE transaction_id IN (
    SELECT id FROM transactions 
    WHERE raw_description LIKE '%RENT%' AND user_id = 'a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11'
);

-- ── Financial Health Score Seed ────────────────────────────────────────────────
-- Pre-computed FHS for the test user based on the seeded transaction data.
-- Metrics rationale:
--   savings_rate=0.33  → 50k avg monthly spending / ~75k estimated income → 33% savings
--   dti_ratio=0.15     → default (no loan data); considered healthy
--   spending_volatility=0.18 → low coefficient of variation across 6 seed months
--   emergency_fund_ratio=0.67 → 2 months available (defaulted), target is 3
-- Score breakdown: savings(25)=41.25pts, DTI(25)=14.6pts, volatility(25)=16pts, EF(25)=16.67pts → 68.5
INSERT INTO financial_health_scores
    (id, user_id, score, savings_rate, dti_ratio, spending_volatility, emergency_fund_ratio, computed_at)
VALUES (
    gen_random_uuid(),
    'a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11',
    68.50,
    0.3333,   -- savings rate (33%)
    0.1500,   -- DTI ratio
    0.1800,   -- spending volatility (coefficient of variation)
    0.6667,   -- emergency fund ratio (2 out of 3 months target)
    now()
) ON CONFLICT DO NOTHING;

-- ── Budget Seed ────────────────────────────────────────────────────────────────
-- Budget rows for the current calendar month.
-- recommended_amount = realistic INR monthly limit per category.
-- limit_amount = 120% of recommended (gives buffer before "over" status).
-- Categories: Groceries(1), Transportation(2), Utilities(3), Entertainment(4),
--             Healthcare(5), Dining(6), Shopping(7), Rent/Housing(11), Insurance(12)
INSERT INTO budgets (id, user_id, category_id, month, recommended_amount, limit_amount)
SELECT
    gen_random_uuid(),
    'a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11',
    cat.category_id,
    DATE_TRUNC('month', CURRENT_DATE)::DATE,
    cat.recommended_amount,
    cat.limit_amount
FROM (VALUES
    (1,  6500.00,  7500.00),   -- Groceries: ₹6,500 recommended / ₹7,500 limit
    (2,  2500.00,  3000.00),   -- Transportation: ₹2,500 / ₹3,000
    (3,  5000.00,  6000.00),   -- Utilities: ₹5,000 / ₹6,000
    (4,  2000.00,  2500.00),   -- Entertainment: ₹2,000 / ₹2,500
    (5,  1500.00,  2000.00),   -- Healthcare: ₹1,500 / ₹2,000
    (6,  4000.00,  5000.00),   -- Dining: ₹4,000 / ₹5,000
    (7,  5000.00,  6500.00),   -- Shopping: ₹5,000 / ₹6,500
    (11, 25000.00, 25000.00),  -- Rent/Housing: fixed ₹25,000 (no buffer needed)
    (12, 5000.00,  5500.00)    -- Insurance: ₹5,000 / ₹5,500
) AS cat(category_id, recommended_amount, limit_amount)
ON CONFLICT (user_id, category_id, month) DO NOTHING;
