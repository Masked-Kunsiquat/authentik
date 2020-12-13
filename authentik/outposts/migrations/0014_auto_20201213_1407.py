# Generated by Django 3.1.4 on 2020-12-13 14:07

from django.apps.registry import Apps
from django.db import migrations
from django.db.backends.base.schema import BaseDatabaseSchemaEditor


def update_config_prefix(apps: Apps, schema_editor: BaseDatabaseSchemaEditor):
    alias = schema_editor.connection.alias
    Outpost = apps.get_model("authentik_outposts", "Outpost")

    for outpost in Outpost.objects.using(alias).all():
        config = outpost._config
        for key in list(config):
            if "passbook" in key:
                new_key = key.replace("passbook", "authentik")
                config[new_key] = config[key]
                del config[key]
        outpost._config = config
        outpost.save()


class Migration(migrations.Migration):

    dependencies = [
        ("authentik_outposts", "0013_auto_20201203_2009"),
    ]

    operations = [migrations.RunPython(update_config_prefix)]
