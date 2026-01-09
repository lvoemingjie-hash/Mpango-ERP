#!/bin/bash
# =========================================================
# Mpango ERP Spec-Kit Project Initialization Script
# Author: Jeff Lee + GPT-5
# Version: 1.0.0
# Date: 2025-10
# =========================================================

echo "🚀 Initializing Mpango ERP project..."

# Step 1. Create project directory
mkdir -p mpango-erp
cd mpango-erp || exit

# Step 2. Copy Spec-Kit file (ensure it is available)
if [ ! -f "../spec-kit_Mpango_ERP.yaml" ]; then
  echo "❌ spec-kit_Mpango_ERP.yaml not found. Please place it in the parent directory."
  exit 1
fi
cp ../spec-kit_Mpango_ERP.yaml ./spec-kit.yaml

# Step 3. Initialize Spec-Kit project
echo "⚙️  Running Spec-Kit initialization..."
spec-kit init mpango-erp --from spec-kit.yaml

# Step 4. Create base folder structure
echo "📁 Creating project folders..."
mkdir -p backend/{api,models,services,utils,tests,config}
mkdir -p frontend/src/{pages,components,store,services}
mkdir -p mobile/{screens,components,services}
mkdir -p database/{migrations,seeds}
mkdir -p infra docs

# Step 5. Add placeholder files
touch backend/main.py frontend/package.json mobile/app.json
touch database/schema.sql infra/docker-compose.yml infra/Dockerfile

# Step 6. Write default README
cat <<EOT >> README.md
# Mpango ERP System

**版本：** 1.0.0  
**作者：** Jeff Lee + GPT-5  
**描述：** 基于 Spec-Kit 构建的批发零售 ERP 系统，用于支持非洲市场的多租户数字化运营。

## 快速启动

```bash
# 启动后端
cd backend
uvicorn app:app --reload

# 启动前端
cd frontend
npm install && npm run dev
```

## 模块说明

- **销售管理 (Sales)**  
  零售商下单、订单跟踪、批发商发货管理。

- **客户关系管理 (CRM)**  
  批发商邀请、客户档案、信用额度管理。

- **库存管理 (Inventory)**  
  库存同步、商品录入、库存调整。

- **采购管理 (Procurement)**  
  供应商管理、采购单、入库记录。
```

EOT

# Step 7. Completion message
echo "✅ Mpango ERP project structure created successfully!"
echo "Next steps:"
echo "1️⃣  Run 'cd backend && uvicorn main:app --reload' to start backend."
echo "2️⃣  Open README.md for further instructions."
echo "3️⃣  Import spec-kit.yaml into Kiro or Coderabbit for AI generation."
