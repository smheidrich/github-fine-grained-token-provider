import asyncio
from contextlib import asynccontextmanager
from datetime import timedelta
from os import environ
from pathlib import Path
from sys import stderr

from github_fine_grained_token_client import (
    GithubCredentials,
    TokenNameError,
    TwoFactorOtpProvider,
    async_client,
)
from tfprovider.level2.attribute_path import ROOT
from tfprovider.level2.diagnostics import Diagnostics
from tfprovider.level3.statically_typed_schema import attribute, attributes_class
from tfprovider.level4.async_provider_servicer import PlanResourceChangeResponse
from tfprovider.level4.async_provider_servicer import Provider as BaseProvider
from tfprovider.level4.async_provider_servicer import Resource as BaseResource


class EnvTwoFactorOtpProvider(TwoFactorOtpProvider):
    async def get_otp_for_user(self, username: str) -> str:
        return environ["GITHUB_OTP"]


@asynccontextmanager
async def credentialed_client():
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
    id: str = attribute(computed=True)
    name: str = attribute(required=True)
    # bar: datetime = attribute(representation=DateAsStringRepr())


class TokenResource(BaseResource):
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
    ) -> PlanResourceChangeResponse[TokenResourceConfig]:
        if prior_state is not None and prior_state.name != config.name:
            requires_replace = [ROOT.attribute_name("name")]
        else:
            requires_replace = None
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
        if config is not None:
            async with credentialed_client() as session:
                try:
                    token_value = await session.create_token(
                        proposed_new_state.name, expires=timedelta(days=1)
                    )
                    diagnostics.add_warning(f"created token: {token_value}")
                except TokenNameError as e:
                    diagnostics.add_warning(f"not creating new token: {e}")
                new_state = TokenResourceConfig(name=config.name)
        else:
            print("DESTROY", file=stderr)
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
    ) -> TokenResourceConfig:
        new_state = None
        async with credentialed_client() as session:
            try:
                token_info = await session.get_token_info_by_name(current_state.name)
                new_state = TokenResourceConfig(
                    name=token_info.name, id=str(token_info.id)
                )
            except KeyError:
                diagnostics.add_warning("token not found, but thats ok")
        return new_state

    async def import_resource(
        self, id: str, diagnostics: Diagnostics
    ) -> TokenResourceConfig:
        async with credentialed_client() as session:
            token_info = await session.get_token_info_by_id(int(id))
        return TokenResourceConfig(id=id, name=token_info.name)


class Provider(BaseProvider):
    provider_state = None
    resource_factories = [TokenResource]
    config_type = ProviderConfig

    schema_version = 1
    block_version = 1

    async def validate_provider_config(
        self, config: ProviderConfig, diagnostics: Diagnostics
    ) -> None:
        print("vpc", file=stderr)


def main():
    s = Provider()
    asyncio.run(s.run())


if __name__ == "__main__":
    main()
