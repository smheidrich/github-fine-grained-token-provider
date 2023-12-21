terraform {
  required_providers {
    githubtok = {
      source = "local/github-fine-grained-token"
      version = "0.1.0"
    }
  }
}

provider "githubtok" {
}

resource githubtok_token "mytoken" {
  provider = githubtok
  name = "sometesttok"
}
