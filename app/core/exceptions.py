class AppError(Exception):
    """Base application exception"""
    pass

class InvalidDomainError(AppError):
    pass

class OTPExpiredError(AppError):
    pass

class TooManyAttemptsError(AppError):
    pass

class CooldownError(AppError):
    pass

class AuthenticationError(AppError):
    pass
