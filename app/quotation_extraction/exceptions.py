class QuotationExtractionError(Exception):
    """Base exception class for all quotation extraction errors."""
    pass


class QuotationParsingError(QuotationExtractionError):
    """Exception raised when parsing of PDF or Excel fails."""
    pass


class QuotationValidationError(QuotationExtractionError):
    """Exception raised when extracted quotation data fails schema or format validation."""
    pass


class QuotationLoaderError(QuotationExtractionError):
    """Exception raised when loading/upserting quotation data to SQL database fails."""
    pass
