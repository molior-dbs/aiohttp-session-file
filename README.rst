aiohttp_session_file
====================

The library provides file sessions store for `aiohttp.web`__.

.. _aiohttp_web: https://aiohttp.readthedocs.io/en/latest/web.html

__ aiohttp_web_

Usage
-----

A trivial usage example:

.. code:: python

    import asyncio
    import shutil
    import tempfile
    import time

    from aiohttp import web
    from aiohttp_session import setup, get_session
    from aiohttp_session_file import FileStorage


    async def handler(request):
        session = await get_session(request)
        last_visit = session['last_visit'] if 'last_visit' in session else None
        session['last_visit'] = time.time()
        text = 'Last visited: {}'.format(last_visit)
        return web.Response(text=text)


    async def setup_dir(app):
        dirpath = tempfile.mkdtemp(prefix='aiohttp-session-')

        async def remove_dir(app):
            shutil.rmtree(dirpath)

        app.on_cleanup.append(remove_dir)
        return dirpath


    async def make_app():
        app = web.Application()

        dirpath = await setup_dir(app)

        max_age = 3600 * 24 * 365  # 1 year
        setup(app, FileStorage(dirpath, max_age=max_age))

        app.router.add_get('/', handler)
        return app


    web.run_app(make_app())

.. NOTE:: Expiry session files need to be cleaned up outside of this tiny library.
          Please refer to `issue#1`_.

.. _`issue#1`: https://github.com/zhangkaizhao/aiohttp-session-file/issues/1
