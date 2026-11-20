# 格湾（LockerBay）

**骨架：** 入柜/取件事件装载 → 格口占用物化 → 超时回收 → 占用账对账

- 领域：数据工程（去皮=事件装载 + 占用状态物化 + 超时闸/回收 + 占用核证）
- 端口：前端 **6100**，接口 **11100**（避开 Chrome 封锁的 6000–6063）
- 公有仓前缀：`lza0829/lockerbay-NN-*`
- 非仓库库存 CRUD、非运单轨迹轴、非营业日封账、非会话窗切分

## 事件类型允许集（`parcel_event_type_allowlist`）

- 允许集版本化落库：`event_type_allowlist_version`（版本/时间/备注）+
  `event_type_allowlist`（版本成员）。默认 v1 = `drop, pickup`，必须保留这两个类型。
- 装载入口在批次开始时固定当前版本，按同一快照分流：集合内事件走既有物化规则；
  集合外事件**只**写 `quarantine`（`kind='event_type'`、`quarantine_key='QT-<事件>'`、
  `allowlist_version`），不入 `parcel_events`、不改 `occupancies` / `cells`。
- 刷新允许集只追加新版本；已物化的占用成员与历史批次快照
  （`ingest_batches.allowlist_version`）不被改写。同一事件重跑不重复搁置。
- 接口：`GET /api/settings/event-types`、`PUT /api/settings/event-types`
  （`{"allowed": [...]}`）、`GET /api/event-type-verify`（版本/违规数/搁置键，只读）。
  柜规页可勾选候选类型（`confirm` / `reclaim`）或填自定义类型后保存。

本地冒烟：

```powershell
cd claude-workspace/lockerbay/_scaffold/backend
pip install -r requirements.txt
$env:DATA_DIR="$PWD/data"; $env:FIXTURES_DIR="$PWD/../fixtures"
python -m uvicorn app.main:app --host 127.0.0.1 --port 11100

cd ../frontend
npm install
npm run dev
```
