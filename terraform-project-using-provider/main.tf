terraform {
  required_providers {
    githubfinetok = {
      source = "local/github-fine-grained-token"
      version = "0.1.0"
    }
  }
}

provider "githubfinetok" {
}

resource githubfinetok_token "mytoken" {
  provider = githubfinetok
  name = "sometesttok"
  expires = "2023-12-30"
  read_permissions = ["contents", "actions"]
}
