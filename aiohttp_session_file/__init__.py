import json
import uuid
from pathlib import Path
from time import time

import aiofiles
from aiohttp_session import AbstractStorage, Session

__version__ = '0.0.2'


class FileStorage(AbstractStorage):
    """File storage"""

    def __init__(self, dirpath, *, cookie_name="AIOHTTP_SESSION",
                 domain=None, max_age=None, path='/',
                 secure=None, httponly=True,
                 key_factory=lambda: uuid.uuid4().hex,
                 encoder=json.dumps, decoder=json.loads):
        super().__init__(cookie_name=cookie_name, domain=domain,
                         max_age=max_age, path=path, secure=secure,
                         httponly=httponly,
                         encoder=encoder, decoder=decoder)
        self._key_factory = key_factory

        self.dirpath = Path(dirpath)
        self.dirpath.mkdir(parents=True, exist_ok=True)

    async def load_session(self, request):
        cookie = self.load_cookie(request)
        if cookie is None:
            return Session(None, data=None, new=True, max_age=self.max_age)
        else:
            key = str(cookie)
            stored_key = self.cookie_name + '_' + key

            filepath = self.dirpath / stored_key

            # expiration file
            expiration_filepath = filepath.with_suffix('.expiration')
            if expiration_filepath.exists():
                async with aiofiles.open(expiration_filepath, 'r') as fp:
                    # Expiration file should not be broken unless file writing
                    # is interrupted and empty file is created.
                    try:
                        expiration = int(await fp.read())
                    except (TypeError, ValueError):
                        expiration = None
                if expiration is None:
                    # remove invalid expiration file
                    expiration_filepath.unlink()

                # The following case should not happen after
                # `self.load_cookie() is not None`.

                # if expiration and expiration < int(time()):  # expired
                #     # The `missing_ok` argument is added in Python 3.8.
                #     # filepath.unlink(missing_ok=True)
                #     try:
                #         filepath.unlink()
                #     except FileNotFoundError:
                #         pass
                #     expiration_filepath.unlink()
                #     return Session(None, data=None,
                #                    new=True, max_age=self.max_age)

                # So expiry session files need to be cleaned up outside of
                # this tiny library.

            if filepath.exists():
                async with aiofiles.open(filepath, 'r') as fp:
                    data = await fp.read()
            else:
                return Session(None, data=None,
                               new=True, max_age=self.max_age)
            try:
                data = self._decoder(data)
            except ValueError:
                data = None
            return Session(key, data=data, new=False, max_age=self.max_age)

    async def save_session(self, request, response, session):
        key = session.identity
        if key is None:
            key = self._key_factory()
            self.save_cookie(response, key,
                             max_age=session.max_age)
        else:
            if session.empty:
                self.save_cookie(response, '',
                                 max_age=session.max_age)
            else:
                key = str(key)
                self.save_cookie(response, key,
                                 max_age=session.max_age)

        data = self._encoder(self._get_session_data(session))
        max_age = session.max_age
        expiration = int(time()) + max_age if max_age is not None else 0
        stored_key = self.cookie_name + '_' + key

        filepath = self.dirpath / stored_key

        if expiration:
            # expiration file
            expiration_filepath = filepath.with_suffix('.expiration')
            async with aiofiles.open(expiration_filepath, 'w') as fp:
                await fp.write(str(expiration))

        async with aiofiles.open(filepath, 'w') as fp:
            await fp.write(data)
