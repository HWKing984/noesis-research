# infra/ · 部署

对齐 `a-Soft/deploy/` 的风格（`docker-compose.yml` + 分服务 Dockerfile + `.env.example`）。

计划纳管：PostgreSQL(+pgvector) · Redis · Neo4j(外部既有实例，只读消费) · api · research-agent · paper-reader · background-worker · web。

**图谱写入不在本编排内**：KG 的导入永远走 `neo4j/scripts/course_graph.py import` 的人工入口。
