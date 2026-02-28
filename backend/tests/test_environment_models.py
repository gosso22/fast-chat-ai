"""
Tests for environment and user role models.
"""

from uuid import uuid4

from app.models.environment import Environment
from app.models.user_role import UserRole, RoleType


class TestEnvironmentModel:
    """Test environment model."""

    def test_environment_creation(self):
        """Test environment model creation with required fields."""
        env = Environment(
            name="test-environment",
            description="A test knowledge base",
            created_by="admin_user",
        )

        assert env.name == "test-environment"
        assert env.description == "A test knowledge base"
        assert env.created_by == "admin_user"

    def test_environment_creation_without_description(self):
        """Test environment model creation without optional description."""
        env = Environment(
            name="minimal-env",
            created_by="admin_user",
        )

        assert env.name == "minimal-env"
        assert env.description is None
        assert env.created_by == "admin_user"

    def test_environment_repr(self):
        """Test environment string representation."""
        env_id = uuid4()
        env = Environment(id=env_id, name="repr-test", created_by="admin")
        assert "repr-test" in repr(env)

    def test_environment_table_name(self):
        """Test that the table name is correct."""
        assert Environment.__tablename__ == "environments"


class TestUserRoleModel:
    """Test user role model."""

    def test_user_role_creation_admin(self):
        """Test creating an admin user role."""
        env_id = uuid4()
        role = UserRole(
            user_id="admin_user",
            role=RoleType.ADMIN,
            environment_id=env_id,
        )

        assert role.user_id == "admin_user"
        assert role.role == RoleType.ADMIN
        assert role.environment_id == env_id

    def test_user_role_creation_chat_user(self):
        """Test creating a chat_user role."""
        env_id = uuid4()
        role = UserRole(
            user_id="chat_user_1",
            role=RoleType.CHAT_USER,
            environment_id=env_id,
        )

        assert role.user_id == "chat_user_1"
        assert role.role == RoleType.CHAT_USER
        assert role.environment_id == env_id

    def test_user_role_repr(self):
        """Test user role string representation."""
        role_id = uuid4()
        role = UserRole(id=role_id, user_id="test", role="admin", environment_id=uuid4())
        assert "test" in repr(role)

    def test_user_role_table_name(self):
        """Test that the table name is correct."""
        assert UserRole.__tablename__ == "user_roles"


class TestRoleTypeEnum:
    """Test role type enum."""

    def test_admin_value(self):
        assert RoleType.ADMIN == "admin"

    def test_chat_user_value(self):
        assert RoleType.CHAT_USER == "chat_user"

    def test_role_type_is_string(self):
        assert isinstance(RoleType.ADMIN, str)
        assert isinstance(RoleType.CHAT_USER, str)


class TestDocumentEnvironmentRelationship:
    """Test that Document model has environment_id field."""

    def test_document_has_environment_id(self):
        """Test that Document model includes environment_id column."""
        from app.models.document import Document

        doc = Document(
            user_id="test_user",
            filename="test.pdf",
            file_size=1024,
            content_type="application/pdf",
            environment_id=uuid4(),
        )
        assert doc.environment_id is not None

    def test_document_environment_id_nullable(self):
        """Test that environment_id is nullable for backward compatibility."""
        from app.models.document import Document

        doc = Document(
            user_id="test_user",
            filename="test.pdf",
            file_size=1024,
            content_type="application/pdf",
        )
        assert doc.environment_id is None
