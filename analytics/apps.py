from django.apps import AppConfig

class AnalyticsConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'analytics'
    verbose_name = 'Analytics & Reports'
    
    def ready(self):
        # Import signals to ensure they are registered
        import analytics.signals