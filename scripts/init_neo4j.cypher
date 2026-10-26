CREATE CONSTRAINT person_uid_unique IF NOT EXISTS FOR (p:Person) REQUIRE p.uid IS UNIQUE;
CREATE CONSTRAINT org_name_unique IF NOT EXISTS FOR (o:Organization) REQUIRE o.name IS UNIQUE;
CREATE INDEX person_name_idx IF NOT EXISTS FOR (p:Person) ON (p.full_name);
CREATE INDEX person_tier_idx IF NOT EXISTS FOR (p:Person) ON (p.reachability_tier);

MERGE (u:Person {full_name: 'SELF_USER'})
ON CREATE SET
  u.uid = '00000000-0000-0000-0000-000000000001',
  u.reachability_tier = 0,
  u.trust_score = 100.0,
  u.verified = true,
  u.created_at = datetime();
