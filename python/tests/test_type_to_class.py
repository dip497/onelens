"""Declared param / return types become edges to the right Class, for Java and Go."""

import pytest

from onelens.importer.graph_writer import _normalize_type


@pytest.mark.parametrize(
    "declared, class_fqn",
    [
        # Java — must keep working exactly as before
        ("com.acme.User", "com.acme.User"),
        ("java.util.List<com.acme.User>", "java.util.List"),
        ("com.acme.User[]", "com.acme.User"),
        ("com.acme.User...", "com.acme.User"),
        ("maps.Region", "maps.Region"),
        ("int", ""),
        ("void", ""),
        ("T", ""),
        # Go — full import paths from the go/types extractor
        ("github.com/acme/agent/internal/contract.JobRequest", "github.com/acme/agent/internal/contract.JobRequest"),
        ("*github.com/acme/agent/internal/server.Client", "github.com/acme/agent/internal/server.Client"),
        ("[]*github.com/acme/agent/internal/server.Client", "github.com/acme/agent/internal/server.Client"),
        ("...github.com/acme/agent/internal/server.Option", "github.com/acme/agent/internal/server.Option"),
        ("github.com/acme/agent/pkg.List[github.com/acme/agent/pkg.Item]", "github.com/acme/agent/pkg.List"),
        ("context.Context", "context.Context"),
        ("map[string]github.com/acme/agent/pkg.Item", ""),
        ("func(context.Context) error", ""),
        ("chan github.com/acme/agent/pkg.Item", ""),
        ("struct{}", ""),
        ("string", ""),
        ("error", ""),
        # C# — Roslyn display strings from the C# extractor
        ("DiscoveryService.DTO.CredentialsList", "DiscoveryService.DTO.CredentialsList"),
        ("System.Collections.Generic.List<DiscoveryService.DTO.CredentialsList>", "System.Collections.Generic.List"),
        ("System.Collections.Generic.Dictionary<string, object>", "System.Collections.Generic.Dictionary"),
        ("DiscoveryService.DTO.Point?", "DiscoveryService.DTO.Point"),
        ("DiscoveryService.DTO.Point[]?", "DiscoveryService.DTO.Point"),
        ("int?", ""),
        ("byte[]", ""),
        ("(int, string)", ""),
        ("DiscoveryService.DTO.Grid[,]", "DiscoveryService.DTO.Grid"),
    ],
)
def test_declared_type_maps_to_class(declared, class_fqn):
    assert _normalize_type(declared) == class_fqn
