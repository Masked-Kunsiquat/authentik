# Generated by Django 5.0.9 on 2024-11-22 14:25

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("authentik_providers_oauth2", "0024_remove_oauth2provider_redirect_uris_and_more"),
    ]

    operations = [
        migrations.RenameField(
            model_name="oauth2provider",
            old_name="jwks_sources",
            new_name="jwt_federation_sources",
        ),
        migrations.AddField(
            model_name="oauth2provider",
            name="jwt_federation_providers",
            field=models.ManyToManyField(
                blank=True, default=None, to="authentik_providers_oauth2.oauth2provider"
            ),
        ),
    ]