# Mpango ERP Spec-Kit 项目初始化模板结构说明

**版本：** 1.0.0  
**作者：** Jeff Lee + GPT-5  
**日期：** 2025年10月  

---

## 一、项目结构总览

```
mpango-erp/
│
├── spec-kit.yaml                 # 数据模型定义（我们已生成）
├── README.md                     # 项目说明与启动指令
│
├── backend/                      # 服务端逻辑
│   ├── app.py                    # 主入口（FastAPI / Flask）
│   ├── config/
│   │   ├── settings.yaml         # 环境配置、数据库连接、多租户设置
│   │   └── secrets.env           # API Keys / 环境变量
│   ├── models/                   # 数据模型（由Spec-Kit生成）
│   ├── api/                      # RESTful接口
│   ├── services/                 # 业务逻辑层
│   ├── utils/                    # 工具与通用模块
│   └── tests/                    # 自动化测试
│
├── frontend/                     # Web管理后台（Vue / React）
│   ├── src/
│   └── package.json
│
├── mobile/                       # 零售商App端（React Native / Flutter）
│   ├── screens/
│   └── app.json
│
├── database/                     # 数据层
│   ├── schema.sql
│   ├── migrations/
│   └── seeds/
│
├── infra/                        # 部署与CI配置
│   ├── docker-compose.yml
│   ├── Dockerfile
│   ├── nginx.conf
│   └── ci-cd.yml
│
└── docs/
    ├── PRD_v1.0.docx
    ├── ERD.png
    └── architecture.md
```

---

## 二、模块说明

| 模块 | 功能说明 | 生成方式 |
|------|-----------|-----------|
| backend/models | 数据表结构 | 由 spec-kit.yaml 自动生成 |
| backend/api | RESTful 接口 | Coderabbit 生成 |
| frontend/pages | 批发商管理界面 | Kiro 模板生成 |
| mobile/screens | 零售商 App 界面 | 未来 AI 自动构建（Phase 2） |
| database/schema.sql | 表结构定义 | Spec-Kit 或 Alembic 生成 |
| infra/docker-compose.yml | 服务部署 | Spec-Kit 模板生成，可一键运行 |

---

## 三、初始化命令

```bash
# 初始化 Spec-Kit 项目
spec-kit init mpango-erp --from spec-kit_Mpango_ERP.yaml

# 启动后端开发服务器
cd backend
uvicorn app:app --reload

# 启动前端
cd frontend
npm install && npm run dev

# 启动移动端（可选）
cd mobile
npm start
```

---

## 四、后续建议

1️⃣ **版本控制**：立即创建 GitHub / GitLab 仓库，命名 `mpango-erp`。  
2️⃣ **持续文档同步**：将 `PRD_v1.0` 与 `spec-kit.yaml` 放入 `/docs`。  
3️⃣ **从销售模块开始**：让 Kiro 生成第一个 API 与模型。  
4️⃣ **API 测试建议**：可使用 Postman，我可辅助你设计请求与验证流程。  

---

**下一步建议：**  
✅ 将此模板文件与 `spec-kit.yaml` 一同导入 Kiro 或本地目录，执行 `spec-kit init` 命令。  
这将为你的 Mpango ERP 创建可直接启动的项目骨架。
