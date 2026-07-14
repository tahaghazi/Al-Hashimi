from django.db import migrations


def set_super_admin(apps, schema_editor):
    User = apps.get_model("users", "CustomUser")
    User.objects.filter(is_superuser=True).update(role="super_admin")


def noop(apps, schema_editor):
    pass


class Migration(migrations.Migration):
    dependencies = [
        ("users", "0007_customuser_role_auditlog"),
    ]
    operations = [migrations.RunPython(set_super_admin, noop)]
