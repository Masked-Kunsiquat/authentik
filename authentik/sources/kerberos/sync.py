"""Sync Kerberos users into authentik"""

from typing import Any

import kadmin
from django.core.exceptions import FieldError
from django.db import IntegrityError, transaction
from structlog.stdlib import BoundLogger, get_logger

from authentik.core.expression.exceptions import (
    PropertyMappingExpressionException,
    SkipObjectException,
)
from authentik.core.models import Group, User, UserTypes
from authentik.core.sources.mapper import SourceMapper
from authentik.events.models import Event, EventAction
from authentik.lib.sync.mapper import PropertyMappingManager
from authentik.lib.sync.outgoing.exceptions import StopSync
from authentik.sources.kerberos.models import (
    KerberosSource,
    Krb5ConfContext,
    UserKerberosSourceConnection,
)


class KerberosSync:
    """Sync Kerberos users into authentik"""

    _source: KerberosSource
    _logger: BoundLogger
    _connection: "kadmin.KAdmin"
    mapper: SourceMapper
    manager: PropertyMappingManager

    def __init__(self, source: KerberosSource):
        self._source = source
        self._connection = self._source.connection()
        self._messages = []
        self._logger = get_logger().bind(source=self._source, syncer=self.__class__.__name__)
        self.mapper = SourceMapper(self._source)
        self.manager = self.mapper.get_manager(User, ["principal"])

    @staticmethod
    def name() -> str:
        """UI name for the type of object this class synchronizes"""
        return "users"

    @property
    def messages(self) -> list[str]:
        """Get all UI messages"""
        return self._messages

    def message(self, *args, **kwargs):
        """Add message that is later added to the System Task and shown to the user"""
        formatted_message = " ".join(args)
        self._messages.append(formatted_message)
        self._logger.warning(*args, **kwargs)

    def _sync_principal(self, principal: str) -> bool:
        try:
            defaults = self.mapper.build_object_properties(
                object_type=User, manager=self.manager, user=None, request=None, principal=principal
            )
            self._logger.debug("Writing user with attributes", **defaults)
            if "username" not in defaults:
                raise IntegrityError("Username was not set by propertymappings")

            groups: list[Group] = []
            group_ids = defaults.pop("groups", [])
            for group_id in group_ids:
                group = self.update_or_create_group(group_id, self.mapper.build_object_properties(
                    object_type=Group, manager=self.manager, user=None, request=None, group_id=group_id, principal=principal,
                ))
                groups.append(group)

            ak_user, created = self.update_or_create_user(principal, defaults, groups)

        except PropertyMappingExpressionException as exc:
            raise StopSync(exc, None, exc.mapping) from exc
        except SkipObjectException:
            return False
        except (IntegrityError, FieldError, TypeError, AttributeError) as exc:
            Event.new(
                EventAction.CONFIGURATION_ERROR,
                message=(f"Failed to create user: {str(exc)} "),
                source=self._source,
                principal=principal,
            ).save()
            return False
        self._logger.debug("Synced User", user=ak_user.username, created=created)
        return True

    def update_or_create_user(self, principal: str, data: dict[str, Any], groups: list[Group]) -> tuple[User, bool]:
        """
        Same as django's update_or_create but correctly update attributes by merging dicts,
        and create a UserKerberosSourceConnection object if needed
        """
        user_source_connection = UserKerberosSourceConnection.objects.filter(
            source=self._source, identifier=principal
        ).first()

        # User doesn't exists
        if not user_source_connection:
            with transaction.atomic():
                user = User.objects.create(**data)
                if user.type == UserTypes.INTERNAL_SERVICE_ACCOUNT:
                    user.set_unusable_password()
                    user.save()
                user_source_connection = UserKerberosSourceConnection.objects.create(
                    source=self._source, user=user, identifier=principal
                )
                user.ak_groups.set(groups)
            return user, True

        user = user_source_connection.user
        user.update_attributes(data)
        with transaction.atomic():
            user.ak_groups.remove(
                *user.ak_groups.filter(groupsourceconnection__source=self._source)
            )
            user.ak_groups.add(*groups)
        return user, False

    def update_or_create_group(self, group_id: str, group_attributes: dict[str, Any | dict[str, Any]]) -> Group:
        # TODO: raise integrity error on group sync fail
        pass

    def sync(self) -> int:
        """Iterate over all Kerberos users and create authentik_core.User instances"""
        if not self._source.enabled or not self._source.sync_users:
            self.message("Source is disabled or user syncing is disabled for this Source")
            return -1

        user_count = 0
        with Krb5ConfContext(self._source):
            for principal in self._connection.principals():
                if self._sync_principal(principal):
                    user_count += 1
        return user_count