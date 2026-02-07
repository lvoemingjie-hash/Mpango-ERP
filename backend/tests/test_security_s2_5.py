"""
S2.5 Batch A: Security Hardening Tests

Tests for:
- Weak SECRET_KEY prevention
- XSS/SQLi input validation
- RBAC enforcement on all endpoints
"""
import pytest
from pydantic import ValidationError

from core.config import Settings
from schemas.user import UserCreateRequest, UserUpdateRequest
from schemas.order import OrderCreateRequest, OrderItemCreate


class TestWeakKeyPrevention:
    """Test S2.5: Weak SECRET_KEY prevention."""
    
    def test_secret_key_too_short(self):
        """Test that SECRET_KEY shorter than 32 characters is rejected."""
        with pytest.raises(ValidationError) as exc_info:
            Settings(
                SECRET_KEY="short_key",
                DATABASE_URL="postgresql://user:pass@localhost:5432/test",
                REDIS_URL="redis://localhost:6379/0",
                MPANGO_ENV="test"
            )
        
        errors = exc_info.value.errors()
        assert any("at least 32 characters" in str(e) for e in errors)
    
    def test_secret_key_contains_weak_substring_secret(self):
        """Test that SECRET_KEY containing 'secret' is rejected."""
        with pytest.raises(ValidationError) as exc_info:
            Settings(
                SECRET_KEY="my_secret_key_that_is_long_enough_12345",
                DATABASE_URL="postgresql://user:pass@localhost:5432/test",
                REDIS_URL="redis://localhost:6379/0",
                MPANGO_ENV="test"
            )
        
        errors = exc_info.value.errors()
        assert any("weak substring" in str(e).lower() for e in errors)
    
    def test_secret_key_contains_weak_substring_password(self):
        """Test that SECRET_KEY containing 'password' is rejected."""
        with pytest.raises(ValidationError) as exc_info:
            Settings(
                SECRET_KEY="password_based_key_long_enough_123456",
                DATABASE_URL="postgresql://user:pass@localhost:5432/test",
                REDIS_URL="redis://localhost:6379/0",
                MPANGO_ENV="test"
            )
        
        errors = exc_info.value.errors()
        assert any("weak substring" in str(e).lower() for e in errors)
    
    def test_secret_key_contains_weak_substring_123456(self):
        """Test that SECRET_KEY containing '123456' is rejected."""
        with pytest.raises(ValidationError) as exc_info:
            Settings(
                SECRET_KEY="my_key_with_123456_in_it_long_enough",
                DATABASE_URL="postgresql://user:pass@localhost:5432/test",
                REDIS_URL="redis://localhost:6379/0",
                MPANGO_ENV="test"
            )
        
        errors = exc_info.value.errors()
        assert any("weak substring" in str(e).lower() for e in errors)
    
    def test_secret_key_contains_weak_substring_changeme(self):
        """Test that SECRET_KEY containing 'change-me' is rejected."""
        with pytest.raises(ValidationError) as exc_info:
            Settings(
                SECRET_KEY="please_change-me_this_is_long_enough_key",
                DATABASE_URL="postgresql://user:pass@localhost:5432/test",
                REDIS_URL="redis://localhost:6379/0",
                MPANGO_ENV="test"
            )
        
        errors = exc_info.value.errors()
        assert any("weak substring" in str(e).lower() for e in errors)
    
    def test_secret_key_contains_weak_substring_default(self):
        """Test that SECRET_KEY containing 'default' is rejected."""
        with pytest.raises(ValidationError) as exc_info:
            Settings(
                SECRET_KEY="default_key_that_is_long_enough_12345",
                DATABASE_URL="postgresql://user:pass@localhost:5432/test",
                REDIS_URL="redis://localhost:6379/0",
                MPANGO_ENV="test"
            )
        
        errors = exc_info.value.errors()
        assert any("weak substring" in str(e).lower() for e in errors)
    
    def test_secret_key_strong_accepted(self):
        """Test that a strong SECRET_KEY is accepted."""
        # This should not raise an exception
        settings = Settings(
            SECRET_KEY="kJ8mN2pQ5rT9vX3zA6bC4dF7gH1jK0lM",  # Strong random key
            DATABASE_URL="postgresql://user:pass@localhost:5432/test",
            REDIS_URL="redis://localhost:6379/0",
            MPANGO_ENV="test"
        )
        
        assert len(settings.SECRET_KEY) >= 32
        assert settings.SECRET_KEY == "kJ8mN2pQ5rT9vX3zA6bC4dF7gH1jK0lM"


class TestXSSPrevention:
    """Test S2.5: XSS prevention in input validation."""
    
    def test_user_full_name_rejects_script_tag(self):
        """Test that full_name rejects <script> tags."""
        with pytest.raises(ValidationError) as exc_info:
            UserCreateRequest(
                email="test@example.com",
                password="securepass123",
                full_name="<script>alert(1)</script>"
            )
        
        errors = exc_info.value.errors()
        assert any("HTML tags" in str(e) or "invalid characters" in str(e) for e in errors)
    
    def test_user_full_name_rejects_html_tags(self):
        """Test that full_name rejects HTML tags."""
        with pytest.raises(ValidationError) as exc_info:
            UserCreateRequest(
                email="test@example.com",
                password="securepass123",
                full_name="<div>John Doe</div>"
            )
        
        errors = exc_info.value.errors()
        assert any("HTML tags" in str(e) or "invalid characters" in str(e) for e in errors)
    
    def test_user_full_name_accepts_safe_input(self):
        """Test that full_name accepts safe input."""
        user = UserCreateRequest(
            email="test@example.com",
            password="securepass123",
            full_name="John Doe"
        )
        
        assert user.full_name == "John Doe"
    
    def test_user_update_full_name_rejects_script_tag(self):
        """Test that UserUpdateRequest full_name rejects <script> tags."""
        with pytest.raises(ValidationError) as exc_info:
            UserUpdateRequest(
                full_name="<script>alert('xss')</script>"
            )
        
        errors = exc_info.value.errors()
        assert any("HTML tags" in str(e) or "invalid characters" in str(e) for e in errors)
    
    def test_order_notes_rejects_script_tag(self):
        """Test that order notes reject <script> tags."""
        with pytest.raises(ValidationError) as exc_info:
            OrderCreateRequest(
                retailer_id="550e8400-e29b-41d4-a716-446655440000",
                items=[
                    OrderItemCreate(
                        product_name="Test Product",
                        sku_code="TEST-001",
                        quantity=1,
                        unit_price=10.00
                    )
                ],
                notes="<script>alert('xss')</script>"
            )
        
        errors = exc_info.value.errors()
        assert any("HTML tags" in str(e) for e in errors)
    
    def test_order_product_name_rejects_script_tag(self):
        """Test that product_name rejects <script> tags."""
        with pytest.raises(ValidationError) as exc_info:
            OrderItemCreate(
                product_name="<script>alert(1)</script>",
                sku_code="TEST-001",
                quantity=1,
                unit_price=10.00
            )
        
        errors = exc_info.value.errors()
        assert any("HTML tags" in str(e) or "invalid characters" in str(e) for e in errors)
    
    def test_order_product_name_accepts_safe_input(self):
        """Test that product_name accepts safe input."""
        item = OrderItemCreate(
            product_name="Premium Coffee Beans",
            sku_code="COFFEE-001",
            quantity=5,
            unit_price=25.50
        )
        
        assert item.product_name == "Premium Coffee Beans"


class TestSQLInjectionPrevention:
    """Test S2.5: SQL injection prevention in input validation."""
    
    def test_user_full_name_rejects_sql_injection_single_quote(self):
        """Test that full_name rejects SQL injection with single quote."""
        with pytest.raises(ValidationError) as exc_info:
            UserCreateRequest(
                email="test@example.com",
                password="securepass123",
                full_name="John' OR '1'='1"
            )
        
        errors = exc_info.value.errors()
        # Should be rejected due to invalid characters (single quote)
        assert any("invalid characters" in str(e) for e in errors)
    
    def test_user_full_name_rejects_sql_injection_comment(self):
        """Test that full_name rejects SQL injection with semicolon."""
        with pytest.raises(ValidationError) as exc_info:
            UserCreateRequest(
                email="test@example.com",
                password="securepass123",
                full_name="John; DROP TABLE users;"
            )
        
        errors = exc_info.value.errors()
        # Should be rejected due to invalid characters (semicolon)
        assert any("invalid characters" in str(e) for e in errors)
    
    def test_order_sku_code_rejects_sql_injection(self):
        """Test that sku_code rejects SQL injection patterns."""
        with pytest.raises(ValidationError) as exc_info:
            OrderItemCreate(
                product_name="Test Product",
                sku_code="TEST'; DROP TABLE orders;--",
                quantity=1,
                unit_price=10.00
            )
        
        errors = exc_info.value.errors()
        # Should be rejected due to invalid characters
        assert any("invalid characters" in str(e) for e in errors)
    
    def test_order_sku_code_accepts_safe_input(self):
        """Test that sku_code accepts safe alphanumeric input."""
        item = OrderItemCreate(
            product_name="Test Product",
            sku_code="PROD-123-ABC",
            quantity=1,
            unit_price=10.00
        )
        
        assert item.sku_code == "PROD-123-ABC"


class TestInputValidationLimits:
    """Test S2.5: Input validation limits to prevent DoS."""
    
    def test_user_password_max_length(self):
        """Test that password has maximum length limit."""
        # Password should have a reasonable max length
        long_password = "a" * 200
        
        with pytest.raises(ValidationError) as exc_info:
            UserCreateRequest(
                email="test@example.com",
                password=long_password,
                full_name="John Doe"
            )
        
        errors = exc_info.value.errors()
        assert any("128" in str(e) or "max_length" in str(e) for e in errors)
    
    def test_order_quantity_max_limit(self):
        """Test that order quantity has maximum limit."""
        with pytest.raises(ValidationError) as exc_info:
            OrderItemCreate(
                product_name="Test Product",
                sku_code="TEST-001",
                quantity=99999,  # Exceeds limit
                unit_price=10.00
            )
        
        errors = exc_info.value.errors()
        assert any("10000" in str(e) or "less than or equal" in str(e) for e in errors)
    
    def test_order_unit_price_max_limit(self):
        """Test that unit_price has maximum limit."""
        with pytest.raises(ValidationError) as exc_info:
            OrderItemCreate(
                product_name="Test Product",
                sku_code="TEST-001",
                quantity=1,
                unit_price=9999999.99  # Exceeds limit
            )
        
        errors = exc_info.value.errors()
        assert any("999999.99" in str(e) or "less than or equal" in str(e) for e in errors)
    
    def test_order_items_max_count(self):
        """Test that order has maximum items limit."""
        items = [
            OrderItemCreate(
                product_name=f"Product {i}",
                sku_code=f"PROD-{i:03d}",
                quantity=1,
                unit_price=10.00
            )
            for i in range(150)  # Exceeds limit of 100
        ]
        
        with pytest.raises(ValidationError) as exc_info:
            OrderCreateRequest(
                retailer_id="550e8400-e29b-41d4-a716-446655440000",
                items=items
            )
        
        errors = exc_info.value.errors()
        assert any("100" in str(e) or "max_length" in str(e) for e in errors)
    
    def test_order_notes_max_length(self):
        """Test that order notes have maximum length."""
        long_notes = "a" * 2000  # Exceeds limit of 1000
        
        with pytest.raises(ValidationError) as exc_info:
            OrderCreateRequest(
                retailer_id="550e8400-e29b-41d4-a716-446655440000",
                items=[
                    OrderItemCreate(
                        product_name="Test Product",
                        sku_code="TEST-001",
                        quantity=1,
                        unit_price=10.00
                    )
                ],
                notes=long_notes
            )
        
        errors = exc_info.value.errors()
        assert any("1000" in str(e) or "max_length" in str(e) for e in errors)


class TestRBACEnforcement:
    """Test S2.5: RBAC enforcement on API endpoints.
    
    Note: These are placeholder tests. Full integration tests would require
    a running application with authentication middleware.
    """
    
    def test_rbac_imports_available(self):
        """Test that RBAC middleware is available for import."""
        from api.middleware.rbac import RequirePermission
        
        # Should not raise ImportError
        assert RequirePermission is not None
    
    def test_orders_endpoints_have_rbac(self):
        """Test that orders endpoints use RequirePermission."""
        import inspect
        from api.v1 import orders
        
        # Check that RequirePermission is imported
        source = inspect.getsource(orders)
        assert "RequirePermission" in source
        assert 'RequirePermission("orders:read")' in source or 'RequirePermission("orders:create")' in source
    
    def test_users_endpoints_have_rbac(self):
        """Test that users endpoints use RequirePermission."""
        import inspect
        from api.v1 import users
        
        # Check that RequirePermission is imported
        source = inspect.getsource(users)
        assert "RequirePermission" in source
        assert 'RequirePermission("users:read")' in source or 'RequirePermission("users:create")' in source
    
    def test_skus_endpoints_have_rbac(self):
        """Test that SKUs endpoints use RequirePermission."""
        import inspect
        from api.v1 import skus
        
        # Check that RequirePermission is imported
        source = inspect.getsource(skus)
        assert "RequirePermission" in source
        assert 'RequirePermission("skus:read")' in source or 'RequirePermission("skus:create")' in source
    
    def test_inventory_endpoints_have_rbac(self):
        """Test that inventory endpoints use RequirePermission."""
        import inspect
        from api.v1 import inventory
        
        # Check that RequirePermission is imported
        source = inspect.getsource(inventory)
        assert "RequirePermission" in source
        assert 'RequirePermission("inventory:read")' in source


class TestSecurityRegression:
    """Test S2.5: Security regression tests."""
    
    def test_no_raw_sql_concatenation(self):
        """Test that codebase doesn't use raw SQL string concatenation."""
        import os
        import re
        
        # Check for dangerous SQL patterns in Python files
        backend_dir = os.path.join(os.path.dirname(__file__), '..')
        
        dangerous_patterns = [
            re.compile(r'execute\(["\']SELECT.*\+'),  # execute("SELECT ... " + var)
            re.compile(r'execute\(["\']INSERT.*\+'),  # execute("INSERT ... " + var)
            re.compile(r'execute\(["\']UPDATE.*\+'),  # execute("UPDATE ... " + var)
            re.compile(r'execute\(["\']DELETE.*\+'),  # execute("DELETE ... " + var)
        ]
        
        violations = []
        
        for root, dirs, files in os.walk(backend_dir):
            # Skip test files, migrations, and virtual environments
            if 'test' in root or 'alembic' in root or '.venv' in root or '__pycache__' in root:
                continue
            
            for file in files:
                if file.endswith('.py'):
                    filepath = os.path.join(root, file)
                    try:
                        with open(filepath, 'r', encoding='utf-8') as f:
                            content = f.read()
                            for pattern in dangerous_patterns:
                                if pattern.search(content):
                                    violations.append(filepath)
                                    break
                    except Exception:
                        pass  # Skip files that can't be read
        
        assert len(violations) == 0, f"Found raw SQL concatenation in: {violations}"
    
    def test_all_string_fields_have_max_length(self):
        """Test that all Pydantic string fields have max_length constraints."""
        from schemas import user, order
        
        # Check UserCreateRequest
        user_create_fields = UserCreateRequest.model_fields
        for field_name, field_info in user_create_fields.items():
            if field_name in ['password', 'full_name']:  # email has EmailStr validation
                # These should have constraints
                assert field_info.metadata or hasattr(field_info, 'max_length'), \
                    f"UserCreateRequest.{field_name} missing max_length constraint"
        
        # Check OrderItemCreate
        order_item_fields = OrderItemCreate.model_fields
        for field_name, field_info in order_item_fields.items():
            if field_name in ['product_name', 'sku_code']:
                # These should have constraints
                assert field_info.metadata or hasattr(field_info, 'max_length'), \
                    f"OrderItemCreate.{field_name} missing max_length constraint"
