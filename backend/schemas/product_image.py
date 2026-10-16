"""Optional display metadata; absence never erases the deletion revision."""
from pydantic import BaseModel


class ProductImageView(BaseModel):
    version: str
    revision: int
    thumb_path: str
    detail_path: str
    width: int
    height: int


class ProductImageState(BaseModel):
    image_revision: int = 0
    image: ProductImageView | None = None


def image_state(row, product_id, *, client=False) -> dict:
    revision = int(row.image_revision) if row is not None else 0
    if row is None or row.current_version is None:
        return {'image_revision': revision, 'image': None}
    prefix = 'client/products' if client else 'catalog-products'
    path = f'/{prefix}/{product_id}/image/{row.current_version}'
    return {'image_revision': revision, 'image': {
        'version': str(row.current_version), 'revision': revision,
        'thumb_path': path + '/thumb', 'detail_path': path + '/detail',
        'width': row.variants['detail']['width'], 'height': row.variants['detail']['height'],
    }}
