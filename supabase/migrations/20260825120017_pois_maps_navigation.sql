-- F6 Maps & Navigation — pois cache/seed support.
--
-- 1. Adds a uniqueness constraint on external_ref so the backend's
--    Google-Places-cache upsert (ON CONFLICT (external_ref) DO UPDATE,
--    app/repositories/pois_repository.py) is atomic and race-safe. NULL
--    external_ref (curated, non-API-sourced rows) is unaffected — Postgres
--    UNIQUE constraints permit any number of NULLs (NULL is never equal to
--    NULL), so this does not restrict the curated rows below or any future
--    admin-curated row.
alter table public.pois add constraint pois_external_ref_key unique (external_ref);

-- 2. Seeds a small set of real, well-known, curated Indian heritage POIs
--    (reference data, coordinates/addresses are genuine — not fabricated
--    business data, same category of seed as migration 20260825120002's
--    `interests` rows) so F6's search/detail/nearby endpoints return
--    genuine results even before a Google Maps Platform API key is
--    configured in a given environment. is_heritage_flagship is
--    deliberately left at its schema default (false): curating the
--    launch flagship narration set is F8's decision to make
--    (IMPLEMENTATION_BLUEPRINT.md F8), not F6's.
insert into public.pois (name, category, location, address, city, region, country, source) values
  ('Taj Mahal', 'heritage', ST_SetSRID(ST_MakePoint(78.0421, 27.1751), 4326)::geography,
    'Dharmapuri, Forest Colony, Tajganj, Agra, Uttar Pradesh 282001', 'Agra', 'Uttar Pradesh', 'India', 'curated'),
  ('Red Fort', 'heritage', ST_SetSRID(ST_MakePoint(77.2410, 28.6562), 4326)::geography,
    'Netaji Subhash Marg, Lal Qila, Chandni Chowk, New Delhi, Delhi 110006', 'Delhi', 'Delhi', 'India', 'curated'),
  ('India Gate', 'heritage', ST_SetSRID(ST_MakePoint(77.2295, 28.6129), 4326)::geography,
    'Rajpath, India Gate, New Delhi, Delhi 110001', 'Delhi', 'Delhi', 'India', 'curated'),
  ('Gateway of India', 'heritage', ST_SetSRID(ST_MakePoint(72.8347, 18.9220), 4326)::geography,
    'Apollo Bandar, Colaba, Mumbai, Maharashtra 400001', 'Mumbai', 'Maharashtra', 'India', 'curated'),
  ('Mysore Palace', 'heritage', ST_SetSRID(ST_MakePoint(76.6552, 12.3052), 4326)::geography,
    'Sayyaji Rao Road, Agrahara, Mysuru, Karnataka 570001', 'Mysuru', 'Karnataka', 'India', 'curated'),
  ('Golden Temple', 'heritage', ST_SetSRID(ST_MakePoint(74.8765, 31.6200), 4326)::geography,
    'Golden Temple Rd, Atta Mandi, Katra Ahluwalia, Amritsar, Punjab 143006', 'Amritsar', 'Punjab', 'India', 'curated'),
  ('Hawa Mahal', 'heritage', ST_SetSRID(ST_MakePoint(75.8267, 26.9239), 4326)::geography,
    'Hawa Mahal Rd, Badi Choupad, J.D.A. Market, Pink City, Jaipur, Rajasthan 302002', 'Jaipur', 'Rajasthan', 'India', 'curated'),
  ('Meenakshi Amman Temple', 'heritage', ST_SetSRID(ST_MakePoint(78.1193, 9.9195), 4326)::geography,
    'Madurai Main, Madurai, Tamil Nadu 625001', 'Madurai', 'Tamil Nadu', 'India', 'curated');
