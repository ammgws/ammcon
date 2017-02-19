# Imports from Python Standard Library
import os.path
# Third party imports
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy_utils import database_exists, create_database
# Ammcon imports
from ammcon.models import Base

LOCAL_PATH = os.environ.get('AMMCON_LOCAL', default=os.path.join(os.path.expanduser("~"), '.ammcon'))
print("Ammcon config dir: {}".format(LOCAL_PATH))


# Setup database
# TO DO: restructure code.
database_uri = 'sqlite:///{}'.format(os.path.join(LOCAL_PATH, 'devices_db.sqlite'))
engine = create_engine(database_uri, echo=False)
if not database_exists(engine.url):
    create_database(engine.url)

# Setup session
# TO DO: restructure code.
Session = sessionmaker()
Session.configure(bind=engine)

# create tables if not already existing
Base.metadata.create_all(engine)
