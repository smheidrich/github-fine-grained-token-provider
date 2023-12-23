import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import date, timedelta
from os import environ
from pathlib import Path
from sys import stderr

from github_fine_grained_token_client import (
    AllRepositories,
    AsyncClientSession,
    FineGrainedTokenIndividualInfo,
    GithubCredentials,
    PermissionValue,
    SelectRepositories,
    TokenNameError,
    TwoFactorOtpProvider,
    async_client,
)
from github_fine_grained_token_client.common import Expired
from github_fine_grained_token_client.permissions import permission_from_str
from tfprovider.level2.attribute_path import ROOT
from tfprovider.level2.diagnostics import Diagnostics
from tfprovider.level2.wire_format import Unknown, UnrefinedUnknown
from tfprovider.level2.wire_representation import (
    DateAsStringWireRepresentation,
    OptionalWireRepresentation,
)
from tfprovider.level3.statically_typed_schema import attribute, attributes_class
from tfprovider.level4.async_provider_servicer import PlanResourceChangeResponse
from tfprovider.level4.async_provider_servicer import Provider as BaseProvider
from tfprovider.level4.async_provider_servicer import Resource as BaseResource


class EnvTwoFactorOtpProvider(TwoFactorOtpProvider):
    async def get_otp_for_user(self, username: str) -> str:
        return environ["GITHUB_OTP"]


@asynccontextmanager
async def credentialed_client() -> AsyncIterator[AsyncClientSession]:
    credentials = GithubCredentials(environ["GITHUB_USER"], environ["GITHUB_PASS"])
    assert credentials.username and credentials.password
    async with async_client(
        credentials=credentials,
        two_factor_otp_provider=EnvTwoFactorOtpProvider(),
        persist_to=Path("~/.github-token-client/persist").expanduser(),
    ) as session:
        yield session


@attributes_class()
class ProviderConfig:
    pass


@attributes_class()
class TokenResourceConfig:
    id: str | None | Unknown = attribute(computed=True)
    name: str = attribute(required=True)
    expires: date | None = attribute(
        optional=True,
        computed=True,
        default=None,
        representation=OptionalWireRepresentation(DateAsStringWireRepresentation()),
    )
    # TODO the only way these are None is if a config is loaded in which they
    #   are not set, but that should be taken care of by the
    #   default_factory/default... so there should be special handling around
    #   Terraform's usage of None values to get around this.
    # TODO computed=True, this is only needed because we apply the
    #   (non-None) default when planning; so compute=True should be set
    #   automatically for anything with a non-None default.
    select_repositories: set[str] | None = attribute(
        default_factory=set, optional=True, computed=True
    )
    read_permissions: set[str] | None = attribute(
        default_factory=set, optional=True, computed=True
    )
    write_permissions: set[str] | None = attribute(
        default_factory=set, optional=True, computed=True
    )


def token_resource_config_from_token_info(
    token_info: FineGrainedTokenIndividualInfo,
) -> TokenResourceConfig:
    return TokenResourceConfig(
        id=str(token_info.id),
        name=token_info.name,
        expires=token_info.expires.date()
        if not isinstance(token_info.expires, Expired)
        else date.today() - timedelta(days=1),
        # TODO not currently returned by GHFGTC => rely on state (overwritten
        #   by values from there at call site)
        select_repositories=set(),
        read_permissions=set(),
        write_permissions=set(),
    )


class TokenResource(BaseResource[None, TokenResourceConfig]):
    type_name = "githubtok_token"
    config_type = TokenResourceConfig

    schema_version = 1
    block_version = 1

    async def validate_resource_config(
        self, config: TokenResourceConfig, diagnostics: Diagnostics
    ) -> None:
        print(f"vrc {config.name=}", file=stderr)

    async def plan_resource_change(
        self,
        prior_state: TokenResourceConfig | None,
        config: TokenResourceConfig,
        proposed_new_state: TokenResourceConfig | None,
        diagnostics: Diagnostics,
    ) -> PlanResourceChangeResponse[TokenResourceConfig] | None:
        if proposed_new_state is None:
            return proposed_new_state
        if proposed_new_state.expires is None:
            proposed_new_state.expires = date.today() + timedelta(days=1)
        if proposed_new_state.select_repositories is None:
            proposed_new_state.select_repositories = set()
        if proposed_new_state.read_permissions is None:
            proposed_new_state.read_permissions = set()
        if proposed_new_state.write_permissions is None:
            proposed_new_state.write_permissions = set()
        # TODO introduce convenience function for this:
        if prior_state is not None and (
            prior_state.name != proposed_new_state.name
            or prior_state.expires != proposed_new_state.expires
            or prior_state.select_repositories != proposed_new_state.select_repositories
            or prior_state.read_permissions != proposed_new_state.read_permissions
            or prior_state.write_permissions != proposed_new_state.write_permissions
        ):
            requires_replace = []
            if prior_state.name != proposed_new_state.name:
                requires_replace.append(ROOT.attribute_name("name"))
            if prior_state.expires != proposed_new_state.expires:
                requires_replace.append(ROOT.attribute_name("expires"))
            if (
                prior_state.select_repositories
                != proposed_new_state.select_repositories
            ):
                requires_replace.append(ROOT.attribute_name("select_repositories"))
            if prior_state.read_permissions != proposed_new_state.read_permissions:
                requires_replace.append(ROOT.attribute_name("read_permissions"))
            if prior_state.write_permissions != proposed_new_state.write_permissions:
                requires_replace.append(ROOT.attribute_name("write_permissions"))
            proposed_new_state.id = UnrefinedUnknown()
        else:
            requires_replace = None
            if proposed_new_state.id is None:
                proposed_new_state.id = UnrefinedUnknown()
        return (
            (proposed_new_state, requires_replace)
            if requires_replace is not None
            else proposed_new_state
        )

    async def apply_resource_change(
        self,
        prior_state: TokenResourceConfig | None,
        config: TokenResourceConfig | None,
        proposed_new_state: TokenResourceConfig | None,
        diagnostics: Diagnostics,
    ) -> TokenResourceConfig | None:
        new_state = None
        async with credentialed_client() as session:
            if proposed_new_state is not None:
                # proposed_new_state is based on config so this must hold:
                assert config is not None
                try:
                    token_value = await session.create_token(
                        proposed_new_state.name,
                        expires=proposed_new_state.expires
                        if proposed_new_state.expires is not None
                        else timedelta(days=1),
                        scope=SelectRepositories(list(rs))
                        if (rs := proposed_new_state.select_repositories)
                        else AllRepositories(),  # TODO allow publ repos
                        permissions={
                            **{
                                permission_from_str(
                                    permission_name
                                ): PermissionValue.READ
                                for permission_name in (
                                    proposed_new_state.read_permissions or set()
                                )
                            },
                            **{
                                permission_from_str(
                                    permission_name
                                ): PermissionValue.WRITE
                                for permission_name in (
                                    proposed_new_state.write_permissions or set()
                                )
                            },
                        },
                    )
                    diagnostics.add_warning(f"created token: {token_value}")
                    token_info = await session.get_token_info_by_name(
                        proposed_new_state.name
                    )
                except TokenNameError as e:
                    diagnostics.add_error(f"not creating new token: {e}")
                    return None
                new_state = token_resource_config_from_token_info(token_info)
                # TODO see comments on these in ^
                new_state.select_repositories = config.select_repositories or set()
                new_state.read_permissions = config.read_permissions or set()
                new_state.write_permissions = config.write_permissions or set()
            else:
                if prior_state is None:
                    return None
                assert isinstance(prior_state.id, str), "bug"
                await session.delete_token_by_id(int(prior_state.id))
        return new_state

    async def upgrade_resource_state(
        self,
        state: TokenResourceConfig,
        version: int,
        diagnostics: Diagnostics,
    ) -> TokenResourceConfig:
        return state

    async def read_resource(
        self, current_state: TokenResourceConfig, diagnostics: Diagnostics
    ) -> TokenResourceConfig | None:
        new_state = None
        async with credentialed_client() as session:
            try:
                token_info = await session.get_token_info_by_name(current_state.name)
                new_state = token_resource_config_from_token_info(token_info)
                # TODO see comments on these in ^
                new_state.select_repositories = (
                    current_state.select_repositories or set()
                )
                new_state.read_permissions = current_state.read_permissions or set()
                new_state.write_permissions = current_state.write_permissions or set()
            except KeyError:
                diagnostics.add_warning("token not found, but thats ok")
        return new_state

    async def import_resource(
        self, id: str, diagnostics: Diagnostics
    ) -> TokenResourceConfig:
        async with credentialed_client() as session:
            token_info = await session.get_token_info_by_id(int(id))
        return TokenResourceConfig(id=id, name=token_info.name)


class Provider(BaseProvider[None, ProviderConfig]):
    provider_state = None
    resource_factories = [TokenResource]
    config_type = ProviderConfig

    schema_version = 1
    block_version = 1

    async def validate_provider_config(
        self, config: ProviderConfig, diagnostics: Diagnostics
    ) -> None:
        print("vpc", file=stderr)


def main() -> None:
    s = Provider()
    asyncio.run(s.run())


if __name__ == "__main__":
    main()
