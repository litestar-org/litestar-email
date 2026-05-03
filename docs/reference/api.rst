API Reference
=============

The main public API is exported through the ``litestar_email`` module.
All classes, functions, and exceptions are available at the top level.

Configuration
-------------

.. automodule:: litestar_email.config
   :members:
   :undoc-members:
   :show-inheritance:

Messages
--------

.. automodule:: litestar_email.message
   :members:
   :undoc-members:
   :show-inheritance:

Service
-------

.. automodule:: litestar_email.service
   :members:
   :undoc-members:
   :show-inheritance:

Plugin
------

.. automodule:: litestar_email.plugin
   :members:
   :undoc-members:
   :show-inheritance:

Exceptions
----------

.. automodule:: litestar_email.exceptions
   :members:
   :undoc-members:
   :show-inheritance:

Backends
--------

The backends are available via ``litestar_email.backends``. Use
``get_backend()`` or ``get_backend_class()`` to obtain backend instances.

.. autofunction:: litestar_email.backends.get_backend

.. autofunction:: litestar_email.backends.get_backend_class

.. autofunction:: litestar_email.backends.email_backend

.. autofunction:: litestar_email.backends.list_backends

.. automodule:: litestar_email.backends.base
   :members:
   :undoc-members:
   :show-inheritance:

.. automodule:: litestar_email.backends.console
   :members:
   :undoc-members:
   :show-inheritance:

.. automodule:: litestar_email.backends.memory
   :members:
   :undoc-members:
   :show-inheritance:

.. automodule:: litestar_email.backends.smtp
   :members:
   :undoc-members:
   :show-inheritance:

.. automodule:: litestar_email.backends.resend
   :members:
   :undoc-members:
   :show-inheritance:

.. automodule:: litestar_email.backends.sendgrid
   :members:
   :undoc-members:
   :show-inheritance:
