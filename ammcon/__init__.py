import os

LOCAL_PATH = os.environ.get('AMMCON_LOCAL', default=os.path.join(os.path.expanduser("~"), '.ammcon'))
print("Ammcon config dir: {}".format(LOCAL_PATH))
