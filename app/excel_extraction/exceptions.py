"""Custom exceptions for the Excel Extraction Agent."""

class ExcelExtractionError(Exception):
    """Base exception for Excel extraction failures."""

class SheetNotFoundError(ExcelExtractionError):
    """Raised when a requested sheet name does not exist in the workbook."""

class NoHeaderFoundError(ExcelExtractionError):
    """Raised when the sheet appears to be completely empty."""

class UnsupportedFormatError(ExcelExtractionError):
    """Raised when the file extension is not a supported spreadsheet format."""
