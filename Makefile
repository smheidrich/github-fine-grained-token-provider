name = github-fine-grained-token
version = 0.1.0
os = linux
arch = amd64
keyid = E02E81251975F4C15B57DF2D05C3C3CA1EE624EF

release_dir = releases/$(version)

.PHONY: install-into-local-filesystem-mirror prepare-release-files clean

install-into-local-filesystem-mirror: \
 $(release_dir)/terraform-provider-$(name)_$(version)_$(os)_$(arch).zip
	mkdir -p ~/.terraform.d/plugins/registry.terraform.io/local/$(name)/
	cp $< ~/.terraform.d/plugins/registry.terraform.io/local/$(name)/

prepare-release-files: \
 $(release_dir)/terraform-provider-$(name)_$(version)_manifest.json \
 $(release_dir)/terraform-provider-$(name)_$(version)_$(os)_$(arch).zip \
 $(release_dir)/terraform-provider-$(name)_$(version)_SHA256SUMS \
 $(release_dir)/terraform-provider-$(name)_$(version)_SHA256SUMS.sig

$(release_dir)/terraform-provider-$(name)_$(version)_SHA256SUMS.sig: \
 $(release_dir)/terraform-provider-$(name)_$(version)_SHA256SUMS
	mkdir -p $(release_dir)
	gpg --detach-sign -u $(keyid) $<

$(release_dir)/terraform-provider-$(name)_$(version)_SHA256SUMS: \
 $(release_dir)/terraform-provider-$(name)_$(version)_$(os)_$(arch).zip
	mkdir -p $(release_dir)
	shasum -a 256 $(release_dir)/*.zip > $@

$(release_dir)/terraform-provider-$(name)_$(version)_manifest.json: \
 manifest.json
	mkdir -p $(release_dir)
	cp $< $@

$(release_dir)/terraform-provider-$(name)_$(version)_$(os)_$(arch).zip:
	mkdir -p $(release_dir)
	mkdir -p tmp
	sed -e 's/\.\././' terraform-plugin/terraform-provider-$(name)_v$(version) > tmp/terraform-provider-$(name)_v$(version)
	chmod +x tmp/terraform-provider-$(name)_v$(version)
	cp -r python-package tmp/
	cd tmp && zip -r ../$@ *

clean:
	rm -rf releases
	rm -rf tmp
