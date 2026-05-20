"""
Configuración compartida para los tests - pytest fixtures
"""
import pytest
import os
import sys
from pathlib import Path

# Agregar el directorio raíz del proyecto al path
sys.path.insert(0, str(Path(__file__).parent.parent))


@pytest.fixture
def app():
    """
    Fixture de la app Flask para tests
    """
    # Configurar variables de entorno para test ANTES de importar
    os.environ['DATABASE_URL'] = 'sqlite:///:memory:'
    
    # Importar la app DESPUÉS de configurar las variables de entorno
    from app.main import app as _app
    from app.database import db
    
    _app.config['TESTING'] = True
    _app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///:memory:'
    _app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    
    with _app.app_context():
        db.create_all()
        yield _app
        db.session.remove()
        db.drop_all()


@pytest.fixture
def app_client(app):
    """
    Crea un cliente de test para hacer requests a la app
    """
    return app.test_client()
