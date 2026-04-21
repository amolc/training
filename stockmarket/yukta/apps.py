from django.apps import AppConfig

class YuktaConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'yukta'

    def ready(self):
        import yukta.tasks   # ✅ ensures tasks are registered