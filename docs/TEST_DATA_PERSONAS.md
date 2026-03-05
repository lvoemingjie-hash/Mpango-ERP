# Mpango ERP v0.2.0 — 测试数据与角色清单

**版本**: v0.2.0  
**场景**: 肯尼亚内罗毕（Nairobi）批发–零售供应链  
**货币**: KES（肯尼亚先令）  
**用途**: Track H 人工验收测试

---

## 1. 批发商（Wholesaler）— 主角

| 字段 | 值 |
|------|-----|
| **公司名称** | Jambo Wholesale Ltd. |
| **地址** | River Road, Nairobi, Kenya |
| **默认货币** | KES (Kenyan Shilling) |
| **管理员账号** | admin@jambo.co.ke |
| **管理员密码** | Password123! |
| **仓库名称** | Main Warehouse |
| **仓库地址** | Plot 42, Enterprise Road, Industrial Area, Nairobi |
| **仓库负责人** | Peter Ochieng |
| **联系电话** | +254 722 100 001 |
| **注册号** | KE-BN-2024-00421 |

---

## 2. 零售商（Retailer）— 测试客户

### 零售商 A — Mama Mboga Shop

| 字段 | 值 |
|------|-----|
| **店铺名称** | Mama Mboga Shop |
| **联系人** | Grace Wanjiku |
| **电话** | +254 712 345 678 |
| **邮箱** | grace@mamammboga.co.ke |
| **密码** | Retail123! |
| **地址** | Stall 17, Gikomba Market, Nairobi |
| **区域** | Gikomba / CBD |
| **类型** | 街边杂货店（Kiosk） |
| **信用额度** | KES 50,000 |

### 零售商 B — Kiosk 254

| 字段 | 值 |
|------|-----|
| **店铺名称** | Kiosk 254 |
| **联系人** | John Kamau |
| **电话** | +254 733 987 654 |
| **邮箱** | john@kiosk254.co.ke |
| **密码** | Retail123! |
| **地址** | Shop 3, Kibera Drive, Kibera |
| **区域** | Kibera |
| **类型** | 社区便利店 |
| **信用额度** | KES 30,000 |

### 零售商 C — Westlands Mini Mart

| 字段 | 值 |
|------|-----|
| **店铺名称** | Westlands Mini Mart |
| **联系人** | Amina Hassan |
| **电话** | +254 700 456 789 |
| **邮箱** | amina@westlandsminimart.co.ke |
| **密码** | Retail123! |
| **地址** | Westlands Road, Suite 12, Westlands |
| **区域** | Westlands |
| **类型** | 中型超市 |
| **信用额度** | KES 150,000 |

### 零售商 D — Eastleigh Duka

| 字段 | 值 |
|------|-----|
| **店铺名称** | Eastleigh Duka |
| **联系人** | Mohamed Abdi |
| **电话** | +254 711 222 333 |
| **邮箱** | mohamed@eastleighduka.co.ke |
| **密码** | Retail123! |
| **地址** | 1st Avenue, Section 3, Eastleigh |
| **区域** | Eastleigh |
| **类型** | 批发零售混合店 |
| **信用额度** | KES 80,000 |

---

## 3. 供应商（Supplier）— 上游

### 供应商 A — Kenya Flour Mills Ltd.

| 字段 | 值 |
|------|-----|
| **公司名称** | Kenya Flour Mills Ltd. |
| **联系人** | David Mwangi |
| **职位** | Sales Manager |
| **电话** | +254 720 111 222 |
| **邮箱** | sales@kenyaflourmills.co.ke |
| **地址** | Thika Road, Ruiru, Kiambu County |
| **支付方式** | 银行转账（30 天账期） |
| **银行账户** | KCB Bank — 1234567890 |
| **供应品类** | 玉米粉、小麦面粉、烘焙粉 |

### 供应商 B — East Africa Edible Oils Co.

| 字段 | 值 |
|------|-----|
| **公司名称** | East Africa Edible Oils Co. |
| **联系人** | Sarah Njeri |
| **职位** | Account Executive |
| **电话** | +254 734 555 666 |
| **邮箱** | orders@eaedibleoils.co.ke |
| **地址** | Mombasa Road, Athi River, Machakos County |
| **支付方式** | 现金 / M-Pesa（货到付款） |
| **M-Pesa Paybill** | 654321 |
| **供应品类** | 食用油（棕榈油、葵花籽油） |

### 供应商 C — Pwani Household Products

| 字段 | 值 |
|------|-----|
| **公司名称** | Pwani Household Products |
| **联系人** | James Otieno |
| **职位** | Distribution Manager |
| **电话** | +254 722 888 999 |
| **邮箱** | distribution@pwani.co.ke |
| **地址** | Changamwe, Mombasa |
| **支付方式** | 银行转账（14 天账期） |
| **银行账户** | Equity Bank — 0987654321 |
| **供应品类** | 洗衣粉、肥皂、洗洁精 |

---

## 4. 商品清单（SKU Catalog）

> ⚠️ **UI 改进建议**：Mpango ERP v0.2.0 的商品管理模块暂不支持图片上传和显示功能。建议在 v0.2.1 中为 Product 实体增加 `image_url` 字段，并在前端商品列表、订单详情页显示缩略图。详见 [附录 A](#附录-a-v021-ui-改进建议商品图片功能)。

### 4.1 粮食类（Cereals & Flour）

| SKU | 商品名称 | 分类 | 单位 | 单价 (KES) | 初始库存 | 图片 URL | 备注 |
|-----|---------|------|------|-----------|---------|---------|------|
| P001 | Unga Maize Meal (2kg) | 粮食 | Bale (12包/箱) | 2,400 | 100 | https://images.unsplash.com/photo-1551754655-cd27e38d2076?w=400 | 肯尼亚主食玉米粉，Jogoo 品牌 |
| P002 | Pembe Wheat Flour (2kg) | 粮食 | Bale (12包/箱) | 2,160 | 80 | https://images.unsplash.com/photo-1574323347407-f5e1ad6d020b?w=400 | 小麦面粉，用于 Chapati |
| P003 | Daawat Basmati Rice (5kg) | 粮食 | Bag (单袋) | 1,200 | 60 | https://images.unsplash.com/photo-1586201375761-83865001e31c?w=400 | 印度进口巴斯马蒂大米 |
| P004 | Soko Maize Meal (1kg) | 粮食 | Bale (24包/箱) | 1,920 | **0** | https://images.unsplash.com/photo-1551754655-cd27e38d2076?w=400 | ⚠️ **缺货** — 测试缺货下单逻辑 |

### 4.2 食用油（Edible Oils）

| SKU | 商品名称 | 分类 | 单位 | 单价 (KES) | 初始库存 | 图片 URL | 备注 |
|-----|---------|------|------|-----------|---------|---------|------|
| P005 | Elianto Sunflower Oil (5L) | 食用油 | Jerrycan (单桶) | 1,850 | 45 | https://images.unsplash.com/photo-1474979266404-7eaacbcd87c5?w=400 | 家庭装葵花籽油 |
| P006 | Rina Cooking Oil (20L) | 食用油 | Jerrycan (单桶) | 5,600 | 20 | https://images.unsplash.com/photo-1474979266404-7eaacbcd87c5?w=400 | 💰 **高价值 SKU** — 餐厅/大客户用 |
| P007 | Fresh Fri Palm Oil (1L) | 食用油 | Carton (12瓶/箱) | 2,400 | **3** | https://images.unsplash.com/photo-1620706857370-e1b9770e8bb1?w=400 | ⚠️ **低库存** — 测试库存不足提示 |

### 4.3 调味料（Seasonings & Spices）

| SKU | 商品名称 | 分类 | 单位 | 单价 (KES) | 初始库存 | 图片 URL | 备注 |
|-----|---------|------|------|-----------|---------|---------|------|
| P008 | Royco Mchuzi Mix (Beef) | 调味料 | Carton (48包/箱) | 1,500 | 50 | https://images.unsplash.com/photo-1596040033229-a9821ebd058d?w=400 | 肯尼亚最畅销炖菜调料 |
| P009 | Kensalt Table Salt (1kg) | 调味料 | Bale (25包/箱) | 625 | 200 | https://images.unsplash.com/photo-1518110925495-5fe2c8e2a9c7?w=400 | 基础调味品，走量大 |
| P010 | Mumias Sugar (2kg) | 调味料 | Bale (10包/箱) | 2,800 | 70 | https://images.unsplash.com/photo-1558642452-9d2a7deb7f62?w=400 | 本地白砂糖 |

### 4.4 日用品（Household Products）

| SKU | 商品名称 | 分类 | 单位 | 单价 (KES) | 初始库存 | 图片 URL | 备注 |
|-----|---------|------|------|-----------|---------|---------|------|
| P011 | Omo Washing Powder (1kg) | 日用品 | Carton (12包/箱) | 3,600 | 35 | https://images.unsplash.com/photo-1582735689369-4fe89db7114c?w=400 | 洗衣粉，家庭装 |
| P012 | Menengai Bar Soap (800g) | 日用品 | Carton (24块/箱) | 2,880 | 40 | https://images.unsplash.com/photo-1600857544200-b2f666a9a2ec?w=400 | 多用途洗衣皂 |
| P013 | Liquid Dish Soap (500ml) | 日用品 | Carton (24瓶/箱) | 3,360 | **0** | https://images.unsplash.com/photo-1585421514284-efb74c2b69ba?w=400 | ⚠️ **缺货** — 测试缺货逻辑 |

### 4.5 饮料（Beverages）

| SKU | 商品名称 | 分类 | 单位 | 单价 (KES) | 初始库存 | 图片 URL | 备注 |
|-----|---------|------|------|-----------|---------|---------|------|
| P014 | Keringet Mineral Water (500ml) | 饮料 | Shrink (24瓶/包) | 480 | 150 | https://images.unsplash.com/photo-1548839140-29a749e1cf4d?w=400 | 矿泉水，走量最大的饮料 |
| P015 | Coca-Cola (500ml PET) | 饮料 | Crate (24瓶/箱) | 1,200 | 90 | https://images.unsplash.com/photo-1629203851122-3726ecdf080e?w=400 | 碳酸饮料 |
| P016 | Tusker Lager (500ml) | 饮料 | Crate (24瓶/箱) | 6,000 | 25 | https://images.unsplash.com/photo-1535958636474-b021ee887b13?w=400 | 💰 **高价值 SKU** — 肯尼亚本地啤酒 |
| P017 | Ketepa Tea Bags (100s) | 饮料 | Carton (24盒/箱) | 7,200 | 15 | https://images.unsplash.com/photo-1556679343-c7306c1976bc?w=400 | 💰 **高价值 SKU** — 肯尼亚红茶 |

---

## 5. 测试场景用商品汇总

### 缺货商品（库存 = 0，用于测试「无法下单」逻辑）

| SKU | 商品名称 | 库存 |
|-----|---------|------|
| P004 | Soko Maize Meal (1kg) | 0 |
| P013 | Liquid Dish Soap (500ml) | 0 |

### 低库存商品（库存 ≤ 5，用于测试「库存不足」提示）

| SKU | 商品名称 | 库存 |
|-----|---------|------|
| P007 | Fresh Fri Palm Oil (1L) | 3 |

### 高价值商品（单价 > 5,000 KES，用于测试大额订单）

| SKU | 商品名称 | 单价 (KES) |
|-----|---------|-----------|
| P006 | Rina Cooking Oil (20L) | 5,600 |
| P016 | Tusker Lager (500ml) Crate | 6,000 |
| P017 | Ketepa Tea Bags (100s) Carton | 7,200 |

---

## 6. 模拟订单场景

### 场景 A：正常订单（Grace Wanjiku → Jambo Wholesale）

| 字段 | 值 |
|------|-----|
| **零售商** | Mama Mboga Shop (Grace Wanjiku) |
| **订单商品** | P001 Unga Maize Meal ×5, P008 Royco Mchuzi Mix ×2, P009 Kensalt Salt ×3 |
| **订单金额** | (2,400×5) + (1,500×2) + (625×3) = KES 16,875 |
| **状态流转** | Draft → Confirmed → Paid → Fulfilled |
| **支付方式** | M-Pesa |
| **M-Pesa 参考号** | QH8923XZLP |

### 场景 B：缺货订单（John Kamau → Jambo Wholesale）

| 字段 | 值 |
|------|-----|
| **零售商** | Kiosk 254 (John Kamau) |
| **订单商品** | P004 Soko Maize Meal ×10 (库存 = 0) |
| **预期结果** | 系统提示「库存不足，无法下单」 |

### 场景 C：大额订单（Amina Hassan → Jambo Wholesale）

| 字段 | 值 |
|------|-----|
| **零售商** | Westlands Mini Mart (Amina Hassan) |
| **订单商品** | P006 Rina Cooking Oil 20L ×10, P017 Ketepa Tea ×5, P015 Coca-Cola ×20 |
| **订单金额** | (5,600×10) + (7,200×5) + (1,200×20) = KES 116,000 |
| **状态流转** | Draft → Confirmed → Paid → Fulfilled |
| **支付方式** | 银行转账 |
| **银行凭证号** | KCB-TXN-20260218-0042 |

### 场景 D：退货场景（Mohamed Abdi → Jambo Wholesale）

| 字段 | 值 |
|------|-----|
| **零售商** | Eastleigh Duka (Mohamed Abdi) |
| **原订单商品** | P012 Menengai Bar Soap ×3 |
| **退货原因** | 收到商品包装破损 |
| **退货数量** | 1 箱 |
| **预期结果** | 订单状态变为 Returned，库存回补 1 箱 |

---

## 7. 模拟支付信息

### M-Pesa 交易参考号示例

| 参考号 | 金额 (KES) | 付款人 | 日期 |
|--------|-----------|--------|------|
| QH8923XZLP | 16,875 | Grace Wanjiku | 2026-02-18 |
| RK4521MNBV | 8,400 | John Kamau | 2026-02-19 |
| TL7832QWER | 116,000 | Amina Hassan | 2026-02-19 |
| SM9045HJKL | 2,880 | Mohamed Abdi | 2026-02-20 |

### 银行转账凭证号示例

| 凭证号 | 金额 (KES) | 银行 | 付款人 | 日期 |
|--------|-----------|------|--------|------|
| KCB-TXN-20260218-0042 | 116,000 | KCB Bank | Westlands Mini Mart | 2026-02-18 |
| EQT-TXN-20260219-0078 | 50,000 | Equity Bank | Eastleigh Duka | 2026-02-19 |

---

## 8. 用户角色与权限矩阵（测试用）

| 角色 | 账号 | 密码 | 可访问模块 |
|------|------|------|-----------|
| **超级管理员** | admin@mpango.demo | DemoAdmin2026! | 全部模块 + 租户管理 |
| **批发商管理员** | admin@jambo.co.ke | Password123! | Home, Sales, Stock, Money, Customers |
| **批发商仓管** | warehouse@jambo.co.ke | Warehouse123! | Home, Stock |
| **批发商财务** | finance@jambo.co.ke | Finance123! | Home, Sales (只读), Money |
| **零售商 A** | grace@mamammboga.co.ke | Retail123! | 商品浏览, 下单, 我的订单, 支付 |
| **零售商 B** | john@kiosk254.co.ke | Retail123! | 商品浏览, 下单, 我的订单, 支付 |
| **零售商 C** | amina@westlandsminimart.co.ke | Retail123! | 商品浏览, 下单, 我的订单, 支付 |
| **零售商 D** | mohamed@eastleighduka.co.ke | Retail123! | 商品浏览, 下单, 我的订单, 支付 |

---

## 附录 A：v0.2.1 UI 改进建议（商品图片功能）

> ⚠️ **当前限制**：  
> Mpango ERP v0.2.0 的商品管理模块暂时不支持图片上传和显示功能。这会影响零售商在浏览商品时的体验，尤其是快速识别商品品牌和包装。

**建议改进**（v0.2.1 优先级：高）：

1. **数据库层**：在 `Product` / `SKU` 实体中增加 `image_url` 字段（`VARCHAR(512)`，存储图片链接）
2. **前端商品列表页**：在每行左侧显示 80×80px 缩略图，无图片时显示默认占位图
3. **前端订单详情页**：在订单行项目中显示商品缩略图，帮助仓管核对发货
4. **商品编辑页**：增加图片上传功能（支持本地上传至云存储，如 AWS S3 / Cloudflare R2）
5. **默认占位图**：为无图片商品显示品类图标（如粮食 🌾、饮料 🥤、日用品 🧴）

**业务价值**：
- 提升零售商下单效率（视觉识别比纯文字快 3 倍）
- 减少因商品混淆导致的退换货率（预计降低 15-20%）
- 增强系统专业度，符合现代电商体验标准
- 为未来移动端 App / PWA 打下基础
