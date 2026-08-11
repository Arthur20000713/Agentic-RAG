# V7 SQLite → MySQL 停机迁移 Runbook

本 runbook 覆盖两次离线迁移：P4 的会话/消息/任务，以及 P6 的 farm/animal/measurement。迁移不做双写；MySQL 切换后 Java 是业务事实源，Python SQLite 不再接受这些业务域的新写入。

## 1. 共同安全规则

1. 安排维护窗口，停止旧 Python 业务写入口并确认没有在途请求。
2. 对源 SQLite 做逐字节备份，不在原文件上操作。
3. 分别计算源文件与备份 SHA-256，二者必须相同。
4. 先执行 `--dry-run`；保存 JSON 报告并人工检查计数、外键和异常项。
5. `--apply` 前确认目标业务表为空。工具默认拒绝向非空目标域导入。
6. apply 使用 MySQL advisory lock 和单事务；失败会回滚本次导入。
7. 成功后保存报告，抽样核对 owner、外键、时间和状态，再切换流量。
8. 成功提交不是自动可逆迁移。需要业务回退时必须依赖事前备份和单独审核的恢复方案，不能直接重跑导入覆盖新数据。

严禁把 SQLite 的 `ON CONFLICT`、`STRFTIME` 或 `PRAGMA` 语义直接复制到 MySQL。

## 2. 备份与校验

以下命令只展示占位路径；不要把真实数据库、备份或报告提交到 Git。

```powershell
$sourceDb = 'C:\maintenance\livestock-source.db'
$backupDb = 'C:\maintenance\backups\livestock-source-before-v7.db'

Copy-Item -LiteralPath $sourceDb -Destination $backupDb
$sourceHash = (Get-FileHash -Algorithm SHA256 -LiteralPath $sourceDb).Hash.ToLowerInvariant()
$backupHash = (Get-FileHash -Algorithm SHA256 -LiteralPath $backupDb).Hash.ToLowerInvariant()
if ($sourceHash -ne $backupHash) { throw 'SQLite backup hash mismatch' }
```

迁移期间不得继续修改 `$sourceDb`。执行 apply 前重新计算 source hash，必须仍等于记录值。

## 3. P4 会话、消息和任务

Dry-run 不连接 MySQL：

```powershell
.venv\Scripts\python.exe scripts\migrate_p4_sqlite_to_mysql.py `
  --source $sourceDb `
  --expected-sha256 $sourceHash `
  --backup $backupDb `
  --dry-run `
  --report C:\maintenance\reports\p4-dry-run.json
```

Apply 需要私网可达的 MySQL，并从环境读取连接参数：

```powershell
$env:MYSQL_HOST = '<maintenance-mysql-host>'
$env:MYSQL_PORT = '3306'
$env:MYSQL_DATABASE = 'livestock_app'
$env:MYSQL_USER = '<migration-user>'
$env:MYSQL_PASSWORD = '<read-from-secret-store>'

.venv\Scripts\python.exe scripts\migrate_p4_sqlite_to_mysql.py `
  --source $sourceDb `
  --expected-sha256 $sourceHash `
  --backup $backupDb `
  --apply `
  --report C:\maintenance\reports\p4-apply.json
```

工具会为无法映射的旧用户创建受控 shadow user/map，并记录 legacy import ledger；不得手工绕过 owner 映射或唯一约束。

## 4. P6 farm、animal 和 measurement

先确认 `target-owner-id` 是已存在且将持有导入业务数据的 Java 用户 ID。

```powershell
.venv\Scripts\python.exe scripts\migrate_p6_livestock_sqlite_to_mysql.py `
  --source $sourceDb `
  --expected-sha256 $sourceHash `
  --target-owner-id <java-user-id> `
  --backup $backupDb `
  --dry-run `
  --report C:\maintenance\reports\p6-dry-run.json
```

确认报告后，在同一维护窗口使用上述 MySQL 环境变量执行：

```powershell
.venv\Scripts\python.exe scripts\migrate_p6_livestock_sqlite_to_mysql.py `
  --source $sourceDb `
  --expected-sha256 $sourceHash `
  --target-owner-id <java-user-id> `
  --backup $backupDb `
  --apply `
  --report C:\maintenance\reports\p6-apply.json
```

## 5. Apply 后对账

至少检查：

- 各源表、导入表和报告中的记录数一致；
- conversation → message/task、farm → animal → measurement 外键完整；
- legacy ID map 唯一且可反查；
- 状态、时间戳、owner 和关键数值抽样一致；
- Java 只读查询可返回导入记录，资源所有权仍生效；
- 迁移后 Python 不再写对应业务表。

自动化证据：

```powershell
.venv\Scripts\python.exe -m pytest `
  tests\integration\test_p4_sqlite_mysql_migration.py `
  tests\integration\test_p6_livestock_sqlite_mysql_migration.py -q
```

## 6. 默认 Compose 的限制

默认 Compose 不发布 MySQL 宿主端口，Python 镜像也不包含迁移脚本。这是刻意的网络边界，因此不能直接从宿主 CLI 对默认 Compose 数据库执行 `--apply`。

生产式迁移应在受控维护网络中提供私网 MySQL endpoint，或另行评审一次性 migration image/Compose profile。不要为了方便长期发布 MySQL 端口，也不要把数据库密码写入命令历史、日志或报告。本仓库已验证迁移算法、事务和对账，但没有宣称完成真实生产数据迁移。
