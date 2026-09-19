USE "vesta_preprocessed_quant";

CREATE VIEW "main"."new_view" AS
SELECT
    *
FROM "main"."source_table"
WHERE 1=1;
