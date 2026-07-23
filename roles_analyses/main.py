import duckdb 

#Creation BDD 
con = duckdb.connect("analyse.duckdb")
con.sql("CREATE OR REPLACE TABLE roles AS SELECT * FROM 'data/roles/role_membership_tree__source__instance.csv'")
con.sql("CREATE OR REPLACE TABLE fonctions AS SELECT * FROM 'data/roles/function_privileges__source__CCPCAM.csv'")
con.sql("CREATE OR REPLACE TABLE droits AS SELECT * FROM 'data/roles/relation_privileges__source__CCPCAM.csv'")
con.sql("CREATE OR REPLACE TABLE droits_avances AS SELECT * FROM 'data/roles/rls_policies_presence__source__CCPCAM.csv'")
con.sql("CREATE OR REPLACE TABLE schemas AS SELECT * FROM 'data/roles/schema_privileges__source__CCPCAM.csv'")

con.sql("CREATE OR REPLACE TABLE connexions_roles AS SELECT * FROM 'data/connexions/connexions.csv'")
con.sql("CREATE OR REPLACE TABLE connexions_detail AS SELECT * FROM 'data/connexions/connexions_detail.csv'")

#con.sql("CREATE OR REPLACE TABLE connexions AS SELECT * FROM ''data/roles/")