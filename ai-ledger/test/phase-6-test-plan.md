# Phase-6 Frontend Test Plan

## Test Engineer Briefing
**Assigned to**: Cloud 4.5 (Test Engineer)
**Date**: 2026-01-13
**Mission**: Validate Phase-6 Frontend Implementation against specifications

## Test Environment Setup

### Prerequisites
1. Backend API running on `http://localhost:8000`
2. Frontend dev server running on `http://localhost:5173`
3. Test users available in backend:
   - Retailer user with tenant access
   - Wholesaler user with tenant access
4. Database with sample orders in different states

### Test Credentials (Example)
```json
{
  "retailer": {
    "tenant_code": "retail-tenant-1",
    "email": "retailer@test.com",
    "password": "test123"
  },
  "wholesaler": {
    "tenant_code": "wholesale-tenant-1",
    "email": "wholesaler@test.com",
    "password": "test123"
  }
}
```

## Test Cases

### 1. Authentication & Login Flow

#### TC-001: Retailer Login
**Objective**: Verify retailer can login and is redirected to correct dashboard
**Steps**:
1. Navigate to `http://localhost:5173`
2. Click login or navigate to `/login`
3. Enter retailer credentials
4. Verify JWT token is stored
5. Verify `/auth/me` is called and role is detected
6. Verify redirect to `/retailer` dashboard

**Expected Results**:
- Login successful
- User redirected to retailer dashboard
- Role displayed as "Retailer"
- Navigation shows retailer-specific options

#### TC-002: Wholesaler Login
**Objective**: Verify wholesaler can login and is redirected to correct dashboard
**Steps**:
1. Navigate to `http://localhost:5173`
2. Login with wholesaler credentials
3. Verify role detection and redirect

**Expected Results**:
- Login successful
- User redirected to wholesaler dashboard
- Role displayed as "Wholesaler"
- Navigation shows wholesaler-specific options

### 2. Role-Based Access Control (RBAC)

#### TC-003: Retailer RBAC Enforcement
**Objective**: Verify retailers cannot access wholesaler features
**Steps**:
1. Login as retailer
2. Try to access `/wholesaler` directly
3. Try to access `/users` directly
4. Verify navigation doesn't show wholesaler options

**Expected Results**:
- Access denied or redirected
- Navigation only shows retailer options
- No user management features visible

#### TC-004: Wholesaler RBAC Enforcement
**Objective**: Verify wholesalers can access all management features
**Steps**:
1. Login as wholesaler
2. Navigate to `/wholesaler`
3. Navigate to `/users`
4. Verify all management options available

**Expected Results**:
- Full access to order management
- User management visible and functional
- All wholesaler features accessible

### 3. Order Management Workflows

#### TC-005: Create Order (Retailer)
**Objective**: Verify retailer can create orders
**Steps**:
1. Login as retailer
2. Navigate to retailer dashboard
3. Fill out create order form with valid data
4. Submit form
5. Verify order appears in order list

**Expected Results**:
- Order created successfully
- Order appears with "pending" status
- Form validation works correctly
- API call to `POST /orders` successful

#### TC-006: Order List View (Both Roles)
**Objective**: Verify both roles can view orders
**Steps**:
1. Login as retailer - verify order list
2. Login as wholesaler - verify order list
3. Check order details modal
4. Verify status badges display correctly

**Expected Results**:
- Orders displayed for both roles
- Status colors: pending (yellow), confirmed (blue), shipped (green), cancelled (red)
- Order details modal shows complete information

#### TC-007: Order State Machine (Wholesaler)
**Objective**: Verify order lifecycle transitions
**Steps**:
1. Login as wholesaler
2. Find order with "pending" status
3. Click "Confirm" - verify status changes to "confirmed"
4. Click "Ship" - verify status changes to "shipped"
5. Test "Cancel" at different stages
6. Verify illegal transitions are blocked

**Expected Results**:
- State transitions work correctly
- Buttons enable/disable based on status
- Cancel available at pending and confirmed stages
- No buttons available for shipped/cancelled orders

### 4. User Management (Wholesaler Only)

#### TC-008: User List Access
**Objective**: Verify wholesaler can view users
**Steps**:
1. Login as wholesaler
2. Navigate to user management
3. Verify user list loads
4. Check role badges and status indicators

**Expected Results**:
- User list displays correctly
- Role badges: wholesaler (purple), retailer (indigo)
- Status indicators: active/inactive
- API call to `GET /users` successful

#### TC-009: User List RBAC (Retailer)
**Objective**: Verify retailers cannot access user management
**Steps**:
1. Login as retailer
2. Try to access `/users`
3. Verify access denied

**Expected Results**:
- Access denied message
- Redirect or fallback UI shown
- 403 error handled correctly

### 5. Error Handling

#### TC-010: API Error Display
**Objective**: Verify backend errors are displayed correctly
**Steps**:
1. Test with invalid credentials (401)
2. Test unauthorized access (403)
3. Test missing resources (404)
4. Test conflict scenarios (409)

**Expected Results**:
- Clear error messages displayed
- User-friendly error handling
- No raw API errors exposed

### 6. Navigation & Routing

#### TC-011: Role-Based Navigation
**Objective**: Verify navigation adapts to user role
**Steps**:
1. Login as retailer - check navigation items
2. Login as wholesaler - check navigation items
3. Verify role-specific options only appear for correct roles

**Expected Results**:
- Retailer sees: Dashboard, Orders, Create Order
- Wholesaler sees: Dashboard, Orders, Order Management, Users
- V0 Playground (dev tool) available to both

#### TC-012: Automatic Role Redirect
**Objective**: Verify automatic redirect based on role
**Steps**:
1. Login as retailer - verify redirect to `/retailer`
2. Login as wholesaler - verify redirect to `/wholesaler`
3. Test direct access to `/` - should redirect appropriately

**Expected Results**:
- Automatic redirect works correctly
- No manual navigation needed after login
- Role detection from `/auth/me` works

## Test Data Requirements

### Backend Test Data Needed
```sql
-- Sample orders in different states
INSERT INTO orders (id, status, user_id, tenant_id, ...) VALUES
('order-1', 'pending', 'user-retailer-1', 'tenant-1'),
('order-2', 'confirmed', 'user-retailer-2', 'tenant-1'),
('order-3', 'shipped', 'user-retailer-1', 'tenant-1'),
('order-4', 'cancelled', 'user-retailer-2', 'tenant-1');

-- Sample users
INSERT INTO users (id, email, role, tenant_id, ...) VALUES
('user-retailer-1', 'retailer@test.com', 'retailer', 'tenant-1'),
('user-wholesaler-1', 'wholesaler@test.com', 'wholesaler', 'tenant-1');
```

## Acceptance Criteria

### Must Pass
- ✅ All 5 MVP workflows functional
- ✅ RBAC properly enforced
- ✅ Order state machine works correctly
- ✅ Error handling displays backend errors
- ✅ Role-based navigation and routing
- ✅ JWT authentication and refresh

### Should Pass
- ✅ UI/UX consistency
- ✅ Responsive design
- ✅ Loading states and feedback
- ✅ Form validation

### May Pass
- ✅ Edge case handling
- ✅ Performance optimization
- ✅ Accessibility features

## Test Report Template

```markdown
# Test Execution Report

**Test Engineer**: Cloud 4.5
**Date**: [DATE]
**Environment**: [URL]

### Test Results Summary
- Total Test Cases: 12
- Passed: [COUNT]
- Failed: [COUNT]
- Blocked: [COUNT]

### Failed Test Cases
[List failed tests with details]

### Blockers
[List any blocking issues]

### Recommendations
[Improvement suggestions]

### Sign-off
[Approval status]
```

## Test Execution Checklist

- [ ] Backend API available and healthy
- [ ] Test users created in database
- [ ] Frontend build successful
- [ ] All test cases executed
- [ ] Defects documented
- [ ] Test report completed
- [ ] Sign-off obtained

---

**Ready for Cloud 4.5 to begin testing!**
