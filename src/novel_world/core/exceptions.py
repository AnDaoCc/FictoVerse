class DomainError(Exception):
    """领域层基础异常。"""


class NotFoundError(DomainError):
    """资源不存在。"""


class ConflictError(DomainError):
    """唯一约束或状态冲突。"""


class ValidationError(DomainError):
    """输入校验失败。"""
