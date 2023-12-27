name = github-fine-grained-token
package_name = github_fine_grained_token_provider
executable_name = github-fine-grained-token-provider
main_module = github_fine_grained_token_provider
version = 0.1.0-rc5
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
	( cd $(release_dir) && shasum -a 256 *.zip *.json > terraform-provider-$(name)_$(version)_SHA256SUMS )

$(release_dir)/terraform-provider-$(name)_$(version)_manifest.json: \
 manifest.json
	mkdir -p $(release_dir)
	cp $< $@

## simple provider launcher script (no terradep):
#$(release_dir)/terraform-provider-$(name)_$(version)_$(os)_$(arch).zip:
	#mkdir -p $(release_dir)
	#mkdir -p tmp
	#sed -e 's/\.\././' terraform-plugin/terraform-provider-$(name)_v$(version) > tmp/terraform-provider-$(name)_v$(version)
	#chmod +x tmp/terraform-provider-$(name)_v$(version)
	#cp -r python-package tmp/
	#cd tmp && zip -r ../$@ *

## provider launcher script using terradep:
#$(release_dir)/terraform-provider-$(name)_$(version)_$(os)_$(arch).zip:
	#mkdir -p $(release_dir)
	#rm -rf tmp
	#mkdir -p tmp
	#terradep-python generate --provider-name $(name) --provider-version $(version) --provider-python-package-name $(package_name) --provider-python-script-name $(executable_name) --provider-env-var-prefix GITHUB_FINE_GRAINED_TOKEN_PROVIDER tmp/
	#( cd python-package && pip3 install --no-deps -t ../tmp/$(package_name) . )
	#cd tmp && zip -r ../$@ *

# provider launcher script using terradep, plus pre-installed relocatable venv:
$(release_dir)/terraform-provider-$(name)_$(version)_$(os)_$(arch).zip:
	mkdir -p $(release_dir)
	rm -rf tmp
	mkdir -p tmp
	terradep-python generate --provider-name $(name) --provider-version $(version) --provider-python-package-name $(package_name) --provider-python-main-module $(main_module) --provider-env-var-prefix GITHUB_FINE_GRAINED_TOKEN_PROVIDER tmp/
	# TODO make exact Python version configurable
	virtualenv -p python3 tmp/venv
	( . tmp/venv/bin/activate && pip3 install ./python-package && virtualenv-make-relocatable tmp/venv )
	cd tmp && zip -r ../$@ *

clean:
	rm -rf releases
	rm -rf tmp
