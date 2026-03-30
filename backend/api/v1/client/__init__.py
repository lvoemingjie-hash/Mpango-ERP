"""Client-facing API module for Retailer App.

Provides view-model APIs for:
- Product browsing (read-only, no cost price exposure)
- Order creation and history (retailer_id derived from JWT, never from request)

Architecture: All endpoints are tenant-aware via JWT tenant claims.
"""
