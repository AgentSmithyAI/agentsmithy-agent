<!-- version list -->

## v1.6.1 (2025-10-22)

### Bug Fixes

- Remove inspector history from indexing
  ([#39](https://github.com/AgentSmithyAI/agentsmithy-agent/pull/39),
  [`18b2173`](https://github.com/AgentSmithyAI/agentsmithy-agent/commit/18b21733f239f4b716bf9f8d0413df480239f3d5))


## v1.6.0 (2025-10-21)

### Features

- Add tool to generate dialogue title
  ([#38](https://github.com/AgentSmithyAI/agentsmithy-agent/pull/38),
  [`2e7ef6f`](https://github.com/AgentSmithyAI/agentsmithy-agent/commit/2e7ef6f2a2828199032f9a1b0a3f6458810c9e7c))


## v1.5.2 (2025-10-20)

### Bug Fixes

- Add changelog flag and fix parser warning
  ([`231993c`](https://github.com/AgentSmithyAI/agentsmithy-agent/commit/231993c05e44a23b6621e68a3c7ffc9eaf3627d3))

- Fix docs & versioning ([#35](https://github.com/AgentSmithyAI/agentsmithy-agent/pull/35),
  [`099dd99`](https://github.com/AgentSmithyAI/agentsmithy-agent/commit/099dd99c001506226061a9fbef3517cad4e149d4))

- Fix pyproject
  ([`ac144ea`](https://github.com/AgentSmithyAI/agentsmithy-agent/commit/ac144eab3194e9415c33f0619988740f0dda067e))

- Fix semantic-release workflow and version management
  ([`33207fa`](https://github.com/AgentSmithyAI/agentsmithy-agent/commit/33207fa26716dab745e1aac23a49da9fb59c0b10))

- Sync version with git tag ([#36](https://github.com/AgentSmithyAI/agentsmithy-agent/pull/36),
  [`121e2b3`](https://github.com/AgentSmithyAI/agentsmithy-agent/commit/121e2b3d62794679302cb87a26acc710ca043add))

- Test semantic-release with changelog generation
  ([`d356a29`](https://github.com/AgentSmithyAI/agentsmithy-agent/commit/d356a293a3cb71340ef10f4486c1e857f3ed682d))

### Chores

- Fix CHANGELOG generation config
  ([`962a2c8`](https://github.com/AgentSmithyAI/agentsmithy-agent/commit/962a2c82f69570b0d102144a98bd73242ec6aa03))

- Fix workflow ([#37](https://github.com/AgentSmithyAI/agentsmithy-agent/pull/37),
  [`f876320`](https://github.com/AgentSmithyAI/agentsmithy-agent/commit/f876320a867cb883e66e46790c1de85fefa327a6))

### Continuous Integration

- Add CODECOV_TOKEN to workflow
  ([`dc9641f`](https://github.com/AgentSmithyAI/agentsmithy-agent/commit/dc9641fe01d7ddcd9efdd5a132981321aea18bc4))

- Trigger workflow for codecov
  ([`f2978be`](https://github.com/AgentSmithyAI/agentsmithy-agent/commit/f2978bef08ace78cb224499da3a7f9d5beb10bec))


## [1.5.1](https://github.com/AgentSmithyAI/agentsmithy-agent/compare/v1.5.0...v1.5.1) (2025-10-20)


### Bug Fixes

* Bug fixes for `tools` and `history` database ([#34](https://github.com/AgentSmithyAI/agentsmithy-agent/issues/34)) ([26e680f](https://github.com/AgentSmithyAI/agentsmithy-agent/commit/26e680f94ff3b99e391da6b0e287f0c3cf387658))

# [1.5.0](https://github.com/AgentSmithyAI/agentsmithy-agent/compare/v1.4.1...v1.5.0) (2025-10-17)


### Features

* Improve providers config ([#28](https://github.com/AgentSmithyAI/agentsmithy-agent/issues/28)) ([5cb2419](https://github.com/AgentSmithyAI/agentsmithy-agent/commit/5cb2419f900062376fc419b4db207293d84076d0))

## [1.4.1](https://github.com/AgentSmithyAI/agentsmithy-agent/compare/v1.4.0...v1.4.1) (2025-10-17)


### Bug Fixes

* Fix history performance ([#27](https://github.com/AgentSmithyAI/agentsmithy-agent/issues/27)) ([6da1ade](https://github.com/AgentSmithyAI/agentsmithy-agent/commit/6da1ade5a5f4fce2fdf37e3ae68f4a8504c7b4f8))

# [1.4.0](https://github.com/AgentSmithyAI/agentsmithy-agent/compare/v1.3.0...v1.4.0) (2025-10-16)


### Features

* History endpoint ([#26](https://github.com/AgentSmithyAI/agentsmithy-agent/issues/26)) ([19296f2](https://github.com/AgentSmithyAI/agentsmithy-agent/commit/19296f2880d9b83caafe6643311d18280b484472))

# [1.3.0](https://github.com/AgentSmithyAI/agentsmithy-agent/compare/v1.2.1...v1.3.0) (2025-10-06)


### Features

* LLM Provider config (preparing for multi provider env) ([#24](https://github.com/AgentSmithyAI/agentsmithy-agent/issues/24)) ([669e575](https://github.com/AgentSmithyAI/agentsmithy-agent/commit/669e57540d78845cf84ba21025f6e6a644bdcae4)), closes [/#diff-7a37f80c434104d6f085d0fefaee55c0a099714cd3b9ec2e22d385f4f85ae193L9-R20](https://github.com///issues/diff-7a37f80c434104d6f085d0fefaee55c0a099714cd3b9ec2e22d385f4f85ae193L9-R20) [/#diff-7a37f80c434104d6f085d0fefaee55c0a099714cd3b9ec2e22d385f4f85ae193L21-R38](https://github.com///issues/diff-7a37f80c434104d6f085d0fefaee55c0a099714cd3b9ec2e22d385f4f85ae193L21-R38) [/#diff-ed1f9cc471a19b5842ff3993dc888b3459d421bfa5f23aa402a85bcbea5e2720L36-R54](https://github.com///issues/diff-ed1f9cc471a19b5842ff3993dc888b3459d421bfa5f23aa402a85bcbea5e2720L36-R54) [/#diff-ed1f9cc471a19b5842ff3993dc888b3459d421bfa5f23aa402a85bcbea5e2720L57-R134](https://github.com///issues/diff-ed1f9cc471a19b5842ff3993dc888b3459d421bfa5f23aa402a85bcbea5e2720L57-R134) [/#diff-ed1f9cc471a19b5842ff3993dc888b3459d421bfa5f23aa402a85bcbea5e2720L97-R207](https://github.com///issues/diff-ed1f9cc471a19b5842ff3993dc888b3459d421bfa5f23aa402a85bcbea5e2720L97-R207) [/#diff-f0489b128d0334e8e79a9086ba82ebe75354401e6a63daf3eb57fcc22b0c962dL3-R4](https://github.com///issues/diff-f0489b128d0334e8e79a9086ba82ebe75354401e6a63daf3eb57fcc22b0c962dL3-R4) [/#diff-3718d43f619450a463403266c38fa9304f7d6a9b7b44b33d3e1e86ac56d9b60fL40-R44](https://github.com///issues/diff-3718d43f619450a463403266c38fa9304f7d6a9b7b44b33d3e1e86ac56d9b60fL40-R44) [/#diff-c63b97c5f7738c33e019c00299169f43e9e9d79d01901882e09b089f1366f83eR1-R5](https://github.com///issues/diff-c63b97c5f7738c33e019c00299169f43e9e9d79d01901882e09b089f1366f83eR1-R5) [/#diff-b5a28976a2c65288aca5cc9e2c1f677ca8b3ba28243ec4cc3cd1420d37dd9ddbL40-R41](https://github.com///issues/diff-b5a28976a2c65288aca5cc9e2c1f677ca8b3ba28243ec4cc3cd1420d37dd9ddbL40-R41) [/#diff-b5a28976a2c65288aca5cc9e2c1f677ca8b3ba28243ec4cc3cd1420d37dd9ddbL58-R69](https://github.com///issues/diff-b5a28976a2c65288aca5cc9e2c1f677ca8b3ba28243ec4cc3cd1420d37dd9ddbL58-R69) [/#diff-b5a28976a2c65288aca5cc9e2c1f677ca8b3ba28243ec4cc3cd1420d37dd9ddbL91-R95](https://github.com///issues/diff-b5a28976a2c65288aca5cc9e2c1f677ca8b3ba28243ec4cc3cd1420d37dd9ddbL91-R95) [/#diff-5f506331561291f61c448f9fe401fbd6e6727e8f9974590de5b53ac5584bc7a9L83](https://github.com///issues/diff-5f506331561291f61c448f9fe401fbd6e6727e8f9974590de5b53ac5584bc7a9L83) [/#diff-ed1f9cc471a19b5842ff3993dc888b3459d421bfa5f23aa402a85bcbea5e2720L10-R10](https://github.com///issues/diff-ed1f9cc471a19b5842ff3993dc888b3459d421bfa5f23aa402a85bcbea5e2720L10-R10)

## [1.2.1](https://github.com/AgentSmithyAI/agentsmithy-agent/compare/v1.2.0...v1.2.1) (2025-10-03)


### Bug Fixes

* Fix configuration reload "on fly" ([#22](https://github.com/AgentSmithyAI/agentsmithy-agent/issues/22)) ([ab3aa97](https://github.com/AgentSmithyAI/agentsmithy-agent/commit/ab3aa9707d47f0232a8b94d57d7ebadf5287e357)), closes [/#diff-2afef500a6c062a4e58bb452daf4209a716e8f5305fb122a664a21e22c969a63R34-R53](https://github.com///issues/diff-2afef500a6c062a4e58bb452daf4209a716e8f5305fb122a664a21e22c969a63R34-R53) [/#diff-9fdcf1bd5eccef720ea7a94f448b962b7625ef9b921b9420e7de6f3fb15d3f7fR149-R150](https://github.com///issues/diff-9fdcf1bd5eccef720ea7a94f448b962b7625ef9b921b9420e7de6f3fb15d3f7fR149-R150) [/#diff-9fdcf1bd5eccef720ea7a94f448b962b7625ef9b921b9420e7de6f3fb15d3f7fL174-R181](https://github.com///issues/diff-9fdcf1bd5eccef720ea7a94f448b962b7625ef9b921b9420e7de6f3fb15d3f7fL174-R181) [/#diff-b10564ab7d2c520cdd0243874879fb0a782862c3c902ab535faabe57d5a505e1L83-L86](https://github.com///issues/diff-b10564ab7d2c520cdd0243874879fb0a782862c3c902ab535faabe57d5a505e1L83-L86) [/#diff-b10564ab7d2c520cdd0243874879fb0a782862c3c902ab535faabe57d5a505e1R205-R206](https://github.com///issues/diff-b10564ab7d2c520cdd0243874879fb0a782862c3c902ab535faabe57d5a505e1R205-R206) [/#diff-7a37f80c434104d6f085d0fefaee55c0a099714cd3b9ec2e22d385f4f85ae193R11](https://github.com///issues/diff-7a37f80c434104d6f085d0fefaee55c0a099714cd3b9ec2e22d385f4f85ae193R11) [/#diff-ed1f9cc471a19b5842ff3993dc888b3459d421bfa5f23aa402a85bcbea5e2720R59-R62](https://github.com///issues/diff-ed1f9cc471a19b5842ff3993dc888b3459d421bfa5f23aa402a85bcbea5e2720R59-R62) [/#diff-3718d43f619450a463403266c38fa9304f7d6a9b7b44b33d3e1e86ac56d9b60fR48-R56](https://github.com///issues/diff-3718d43f619450a463403266c38fa9304f7d6a9b7b44b33d3e1e86ac56d9b60fR48-R56) [/#diff-3718d43f619450a463403266c38fa9304f7d6a9b7b44b33d3e1e86ac56d9b60fR70](https://github.com///issues/diff-3718d43f619450a463403266c38fa9304f7d6a9b7b44b33d3e1e86ac56d9b60fR70) [/#diff-3718d43f619450a463403266c38fa9304f7d6a9b7b44b33d3e1e86ac56d9b60fR93-R96](https://github.com///issues/diff-3718d43f619450a463403266c38fa9304f7d6a9b7b44b33d3e1e86ac56d9b60fR93-R96) [/#diff-52535c904f829474e1b1c3cfb0f71d5f3188f936a60d9e47d003547cddee1982L45-R52](https://github.com///issues/diff-52535c904f829474e1b1c3cfb0f71d5f3188f936a60d9e47d003547cddee1982L45-R52) [/#diff-2afef500a6c062a4e58bb452daf4209a716e8f5305fb122a664a21e22c969a63R34-R53](https://github.com///issues/diff-2afef500a6c062a4e58bb452daf4209a716e8f5305fb122a664a21e22c969a63R34-R53) [/#diff-bdd4bc7a33a61bf0fc4a682b15a04205a3ca4c0710d6bdbc5156c66ae1b0d653R59-R63](https://github.com///issues/diff-bdd4bc7a33a61bf0fc4a682b15a04205a3ca4c0710d6bdbc5156c66ae1b0d653R59-R63) [/#diff-9fdcf1bd5eccef720ea7a94f448b962b7625ef9b921b9420e7de6f3fb15d3f7fR52](https://github.com///issues/diff-9fdcf1bd5eccef720ea7a94f448b962b7625ef9b921b9420e7de6f3fb15d3f7fR52) [/#diff-9fdcf1bd5eccef720ea7a94f448b962b7625ef9b921b9420e7de6f3fb15d3f7fR149-R150](https://github.com///issues/diff-9fdcf1bd5eccef720ea7a94f448b962b7625ef9b921b9420e7de6f3fb15d3f7fR149-R150)

# [1.2.0](https://github.com/AgentSmithyAI/agentsmithy-agent/compare/v1.1.2...v1.2.0) (2025-10-03)


### Features

* Agent launch improvements ([#20](https://github.com/AgentSmithyAI/agentsmithy-agent/issues/20)) ([981b26a](https://github.com/AgentSmithyAI/agentsmithy-agent/commit/981b26ab7e903cf09c6c029cc9aa3ec172d00a1e))

## [1.1.2](https://github.com/AgentSmithyAI/agentsmithy-agent/compare/v1.1.1...v1.1.2) (2025-10-01)


### Bug Fixes

* Improve agent tools flow ([#19](https://github.com/AgentSmithyAI/agentsmithy-agent/issues/19)) ([952b9f5](https://github.com/AgentSmithyAI/agentsmithy-agent/commit/952b9f510add69ad209d2d80d33245f6ce4c2e6c))

## [1.1.1](https://github.com/AgentSmithyAI/agentsmithy-agent/compare/v1.1.0...v1.1.1) (2025-09-30)


### Bug Fixes

* Improve build & run flow ([#18](https://github.com/AgentSmithyAI/agentsmithy-agent/issues/18)) ([d08c6b5](https://github.com/AgentSmithyAI/agentsmithy-agent/commit/d08c6b52169839f34c4f1f7304298fdc85e89a9d)), closes [/#diff-fde0e5d64aae13964fdda6d47af304cf1a7015cbc17e440ac4a5e662ee1d875eR35-R44](https://github.com///issues/diff-fde0e5d64aae13964fdda6d47af304cf1a7015cbc17e440ac4a5e662ee1d875eR35-R44) [/#diff-fde0e5d64aae13964fdda6d47af304cf1a7015cbc17e440ac4a5e662ee1d875eR78-R86](https://github.com///issues/diff-fde0e5d64aae13964fdda6d47af304cf1a7015cbc17e440ac4a5e662ee1d875eR78-R86) [/#diff-fde0e5d64aae13964fdda6d47af304cf1a7015cbc17e440ac4a5e662ee1d875eR200-R257](https://github.com///issues/diff-fde0e5d64aae13964fdda6d47af304cf1a7015cbc17e440ac4a5e662ee1d875eR200-R257) [/#diff-76ed074a9305c04054cdebb9e9aad2d818052b07091de1f20cad0bbac34ffb52R7-R11](https://github.com///issues/diff-76ed074a9305c04054cdebb9e9aad2d818052b07091de1f20cad0bbac34ffb52R7-R11) [/#diff-76ed074a9305c04054cdebb9e9aad2d818052b07091de1f20cad0bbac34ffb52R50-R120](https://github.com///issues/diff-76ed074a9305c04054cdebb9e9aad2d818052b07091de1f20cad0bbac34ffb52R50-R120) [/#diff-fde0e5d64aae13964fdda6d47af304cf1a7015cbc17e440ac4a5e662ee1d875eR267-R303](https://github.com///issues/diff-fde0e5d64aae13964fdda6d47af304cf1a7015cbc17e440ac4a5e662ee1d875eR267-R303) [/#diff-76ed074a9305c04054cdebb9e9aad2d818052b07091de1f20cad0bbac34ffb52R50-R120](https://github.com///issues/diff-76ed074a9305c04054cdebb9e9aad2d818052b07091de1f20cad0bbac34ffb52R50-R120) [/#diff-b10564ab7d2c520cdd0243874879fb0a782862c3c902ab535faabe57d5a505e1L22-R32](https://github.com///issues/diff-b10564ab7d2c520cdd0243874879fb0a782862c3c902ab535faabe57d5a505e1L22-R32) [/#diff-b10564ab7d2c520cdd0243874879fb0a782862c3c902ab535faabe57d5a505e1L38-R48](https://github.com///issues/diff-b10564ab7d2c520cdd0243874879fb0a782862c3c902ab535faabe57d5a505e1L38-R48) [/#diff-b10564ab7d2c520cdd0243874879fb0a782862c3c902ab535faabe57d5a505e1L55-L63](https://github.com///issues/diff-b10564ab7d2c520cdd0243874879fb0a782862c3c902ab535faabe57d5a505e1L55-L63)

# [1.1.0](https://github.com/AgentSmithyAI/agentsmithy-agent/compare/v1.0.3...v1.1.0) (2025-09-30)


### Features

* Enchance history ([#17](https://github.com/AgentSmithyAI/agentsmithy-agent/issues/17)) ([145bea9](https://github.com/AgentSmithyAI/agentsmithy-agent/commit/145bea96edeed8af9201244d374e9ff9667c5a69)), closes [/#diff-5f506331561291f61c448f9fe401fbd6e6727e8f9974590de5b53ac5584bc7a9L12-R27](https://github.com///issues/diff-5f506331561291f61c448f9fe401fbd6e6727e8f9974590de5b53ac5584bc7a9L12-R27) [/#diff-5f506331561291f61c448f9fe401fbd6e6727e8f9974590de5b53ac5584bc7a9L44-R54](https://github.com///issues/diff-5f506331561291f61c448f9fe401fbd6e6727e8f9974590de5b53ac5584bc7a9L44-R54) [/#diff-63e92f380378c1854886548e1b93d1984a4c54024b8b337a9d220ffe8b05bd52L20-R24](https://github.com///issues/diff-63e92f380378c1854886548e1b93d1984a4c54024b8b337a9d220ffe8b05bd52L20-R24) [/#diff-63e92f380378c1854886548e1b93d1984a4c54024b8b337a9d220ffe8b05bd52L166-R92](https://github.com///issues/diff-63e92f380378c1854886548e1b93d1984a4c54024b8b337a9d220ffe8b05bd52L166-R92) [/#diff-7449196f048aa0598711a82ff4d1d898d99b1173ef63ea3be5c7ce5183bb133aL84-R125](https://github.com///issues/diff-7449196f048aa0598711a82ff4d1d898d99b1173ef63ea3be5c7ce5183bb133aL84-R125) [/#diff-7449196f048aa0598711a82ff4d1d898d99b1173ef63ea3be5c7ce5183bb133aL97-R158](https://github.com///issues/diff-7449196f048aa0598711a82ff4d1d898d99b1173ef63ea3be5c7ce5183bb133aL97-R158) [/#diff-7449196f048aa0598711a82ff4d1d898d99b1173ef63ea3be5c7ce5183bb133aR171-R176](https://github.com///issues/diff-7449196f048aa0598711a82ff4d1d898d99b1173ef63ea3be5c7ce5183bb133aR171-R176) [/#diff-63e92f380378c1854886548e1b93d1984a4c54024b8b337a9d220ffe8b05bd52L34-R50](https://github.com///issues/diff-63e92f380378c1854886548e1b93d1984a4c54024b8b337a9d220ffe8b05bd52L34-R50) [/#diff-5f506331561291f61c448f9fe401fbd6e6727e8f9974590de5b53ac5584bc7a9L12-R27](https://github.com///issues/diff-5f506331561291f61c448f9fe401fbd6e6727e8f9974590de5b53ac5584bc7a9L12-R27) [/#diff-5f506331561291f61c448f9fe401fbd6e6727e8f9974590de5b53ac5584bc7a9L44-R54](https://github.com///issues/diff-5f506331561291f61c448f9fe401fbd6e6727e8f9974590de5b53ac5584bc7a9L44-R54) [/#diff-63e92f380378c1854886548e1b93d1984a4c54024b8b337a9d220ffe8b05bd52L34-R50](https://github.com///issues/diff-63e92f380378c1854886548e1b93d1984a4c54024b8b337a9d220ffe8b05bd52L34-R50) [/#diff-667e564832a0547cce837ce9b05112f4f47d4b4e599650da2185daaf76eb11b9R5-R13](https://github.com///issues/diff-667e564832a0547cce837ce9b05112f4f47d4b4e599650da2185daaf76eb11b9R5-R13) [/#diff-667e564832a0547cce837ce9b05112f4f47d4b4e599650da2185daaf76eb11b9R31-R54](https://github.com///issues/diff-667e564832a0547cce837ce9b05112f4f47d4b4e599650da2185daaf76eb11b9R31-R54) [/#diff-2afef500a6c062a4e58bb452daf4209a716e8f5305fb122a664a21e22c969a63L41-R46](https://github.com///issues/diff-2afef500a6c062a4e58bb452daf4209a716e8f5305fb122a664a21e22c969a63L41-R46) [/#diff-2afef500a6c062a4e58bb452daf4209a716e8f5305fb122a664a21e22c969a63R68-R80](https://github.com///issues/diff-2afef500a6c062a4e58bb452daf4209a716e8f5305fb122a664a21e22c969a63R68-R80) [/#diff-2afef500a6c062a4e58bb452daf4209a716e8f5305fb122a664a21e22c969a63R12](https://github.com///issues/diff-2afef500a6c062a4e58bb452daf4209a716e8f5305fb122a664a21e22c969a63R12) [/#diff-2afef500a6c062a4e58bb452daf4209a716e8f5305fb122a664a21e22c969a63R68-R80](https://github.com///issues/diff-2afef500a6c062a4e58bb452daf4209a716e8f5305fb122a664a21e22c969a63R68-R80) [/#diff-a387fb2fbbece7e00db2efa082a17425069d3d7cd22ce9b5db60c1a38252d5ffL12-R12](https://github.com///issues/diff-a387fb2fbbece7e00db2efa082a17425069d3d7cd22ce9b5db60c1a38252d5ffL12-R12) [/#diff-76ed074a9305c04054cdebb9e9aad2d818052b07091de1f20cad0bbac34ffb52L28-R37](https://github.com///issues/diff-76ed074a9305c04054cdebb9e9aad2d818052b07091de1f20cad0bbac34ffb52L28-R37)

## [1.0.3](https://github.com/AgentSmithyAI/agentsmithy-agent/compare/v1.0.2...v1.0.3) (2025-09-23)


### Bug Fixes

* Remove "latest" tag from release artefacts ([#16](https://github.com/AgentSmithyAI/agentsmithy-agent/issues/16)) ([1d81b37](https://github.com/AgentSmithyAI/agentsmithy-agent/commit/1d81b372bd3036f29e5ff5987c46ae4031ee2014))

## [1.0.2](https://github.com/AgentSmithyAI/agentsmithy-agent/compare/v1.0.1...v1.0.2) (2025-09-22)


### Bug Fixes

* Fix github workflow ([#15](https://github.com/AgentSmithyAI/agentsmithy-agent/issues/15)) ([4c834ae](https://github.com/AgentSmithyAI/agentsmithy-agent/commit/4c834ae085d3b03bdbec7e3ab9d726e697ccd4f3))

## [1.0.1](https://github.com/AgentSmithyAI/agentsmithy-local/compare/v1.0.0...v1.0.1) (2025-09-22)


### Bug Fixes

* Fix github workflow ([#14](https://github.com/AgentSmithyAI/agentsmithy-local/issues/14)) ([2f53c3d](https://github.com/AgentSmithyAI/agentsmithy-local/commit/2f53c3df99f1256bc78937f8803fdc7a19f44c89)), closes [/#diff-fde0e5d64aae13964fdda6d47af304cf1a7015cbc17e440ac4a5e662ee1d875eL1-R1](https://github.com///issues/diff-fde0e5d64aae13964fdda6d47af304cf1a7015cbc17e440ac4a5e662ee1d875eL1-R1) [/#diff-fde0e5d64aae13964fdda6d47af304cf1a7015cbc17e440ac4a5e662ee1d875eL18-R26](https://github.com///issues/diff-fde0e5d64aae13964fdda6d47af304cf1a7015cbc17e440ac4a5e662ee1d875eL18-R26) [/#diff-fde0e5d64aae13964fdda6d47af304cf1a7015cbc17e440ac4a5e662ee1d875eL35-R59](https://github.com///issues/diff-fde0e5d64aae13964fdda6d47af304cf1a7015cbc17e440ac4a5e662ee1d875eL35-R59) [/#diff-fde0e5d64aae13964fdda6d47af304cf1a7015cbc17e440ac4a5e662ee1d875eL68-R91](https://github.com///issues/diff-fde0e5d64aae13964fdda6d47af304cf1a7015cbc17e440ac4a5e662ee1d875eL68-R91) [/#diff-fde0e5d64aae13964fdda6d47af304cf1a7015cbc17e440ac4a5e662ee1d875eL135-R148](https://github.com///issues/diff-fde0e5d64aae13964fdda6d47af304cf1a7015cbc17e440ac4a5e662ee1d875eL135-R148) [/#diff-fde0e5d64aae13964fdda6d47af304cf1a7015cbc17e440ac4a5e662ee1d875eL150-R157](https://github.com///issues/diff-fde0e5d64aae13964fdda6d47af304cf1a7015cbc17e440ac4a5e662ee1d875eL150-R157) [/#diff-fde0e5d64aae13964fdda6d47af304cf1a7015cbc17e440ac4a5e662ee1d875eL193-R229](https://github.com///issues/diff-fde0e5d64aae13964fdda6d47af304cf1a7015cbc17e440ac4a5e662ee1d875eL193-R229) [/#diff-fde0e5d64aae13964fdda6d47af304cf1a7015cbc17e440ac4a5e662ee1d875eL229-R239](https://github.com///issues/diff-fde0e5d64aae13964fdda6d47af304cf1a7015cbc17e440ac4a5e662ee1d875eL229-R239) [/#diff-fde0e5d64aae13964fdda6d47af304cf1a7015cbc17e440ac4a5e662ee1d875eL239-R249](https://github.com///issues/diff-fde0e5d64aae13964fdda6d47af304cf1a7015cbc17e440ac4a5e662ee1d875eL239-R249) [/#diff-fde0e5d64aae13964fdda6d47af304cf1a7015cbc17e440ac4a5e662ee1d875eL68-R91](https://github.com///issues/diff-fde0e5d64aae13964fdda6d47af304cf1a7015cbc17e440ac4a5e662ee1d875eL68-R91) [/#diff-fde0e5d64aae13964fdda6d47af304cf1a7015cbc17e440ac4a5e662ee1d875eL99-R121](https://github.com///issues/diff-fde0e5d64aae13964fdda6d47af304cf1a7015cbc17e440ac4a5e662ee1d875eL99-R121) [/#diff-fde0e5d64aae13964fdda6d47af304cf1a7015cbc17e440ac4a5e662ee1d875eR166-R187](https://github.com///issues/diff-fde0e5d64aae13964fdda6d47af304cf1a7015cbc17e440ac4a5e662ee1d875eR166-R187) [/#diff-fde0e5d64aae13964fdda6d47af304cf1a7015cbc17e440ac4a5e662ee1d875eL99-R121](https://github.com///issues/diff-fde0e5d64aae13964fdda6d47af304cf1a7015cbc17e440ac4a5e662ee1d875eL99-R121) [/#diff-fde0e5d64aae13964fdda6d47af304cf1a7015cbc17e440ac4a5e662ee1d875eL193-R229](https://github.com///issues/diff-fde0e5d64aae13964fdda6d47af304cf1a7015cbc17e440ac4a5e662ee1d875eL193-R229) [/#diff-fde0e5d64aae13964fdda6d47af304cf1a7015cbc17e440ac4a5e662ee1d875eL229-R239](https://github.com///issues/diff-fde0e5d64aae13964fdda6d47af304cf1a7015cbc17e440ac4a5e662ee1d875eL229-R239) [/#diff-fde0e5d64aae13964fdda6d47af304cf1a7015cbc17e440ac4a5e662ee1d875eL239-R249](https://github.com///issues/diff-fde0e5d64aae13964fdda6d47af304cf1a7015cbc17e440ac4a5e662ee1d875eL239-R249)

# 1.0.0 (2025-09-21)


### Bug Fixes

* File tools fixes ([#6](https://github.com/AgentSmithyAI/agentsmithy-local/issues/6)) ([d5e1c6f](https://github.com/AgentSmithyAI/agentsmithy-local/commit/d5e1c6f02b1192c3d2699137635e31aeecdfc857))
* Fixes for mvp ([#8](https://github.com/AgentSmithyAI/agentsmithy-local/issues/8)) ([93626f1](https://github.com/AgentSmithyAI/agentsmithy-local/commit/93626f192d3cc1c6de586c57e568e5ec59d164e4))
* Remove unused search SSE event && CI/CD ([#11](https://github.com/AgentSmithyAI/agentsmithy-local/issues/11)) ([878bc85](https://github.com/AgentSmithyAI/agentsmithy-local/commit/878bc85a62cf0c65ee9d60af2a9dd1c87629cbcd)), closes [/#diff-bdd4bc7a33a61bf0fc4a682b15a04205a3ca4c0710d6bdbc5156c66ae1b0d653L55-R55](https://github.com///issues/diff-bdd4bc7a33a61bf0fc4a682b15a04205a3ca4c0710d6bdbc5156c66ae1b0d653L55-R55) [/#diff-bdd4bc7a33a61bf0fc4a682b15a04205a3ca4c0710d6bdbc5156c66ae1b0d653L98-R99](https://github.com///issues/diff-bdd4bc7a33a61bf0fc4a682b15a04205a3ca4c0710d6bdbc5156c66ae1b0d653L98-R99) [/#diff-bdd4bc7a33a61bf0fc4a682b15a04205a3ca4c0710d6bdbc5156c66ae1b0d653L150-R148](https://github.com///issues/diff-bdd4bc7a33a61bf0fc4a682b15a04205a3ca4c0710d6bdbc5156c66ae1b0d653L150-R148) [/#diff-65fe3568510a26aa7bfedd8f518eabd23f84fb55ae8fa7f0f8474634be1d2250L27-R27](https://github.com///issues/diff-65fe3568510a26aa7bfedd8f518eabd23f84fb55ae8fa7f0f8474634be1d2250L27-R27) [/#diff-f7d1c049ca35b9a5ef3a5a365381cc9be0f81f38e63d5bbae0c3b18082006beeL11-R11](https://github.com///issues/diff-f7d1c049ca35b9a5ef3a5a365381cc9be0f81f38e63d5bbae0c3b18082006beeL11-R11) [/#diff-f7d1c049ca35b9a5ef3a5a365381cc9be0f81f38e63d5bbae0c3b18082006beeL75-R77](https://github.com///issues/diff-f7d1c049ca35b9a5ef3a5a365381cc9be0f81f38e63d5bbae0c3b18082006beeL75-R77) [/#diff-2be4e51c5eb5feeab838e0d02b909d5e7177e12b12e5ae2a35e618e501c3b19dL59-R60](https://github.com///issues/diff-2be4e51c5eb5feeab838e0d02b909d5e7177e12b12e5ae2a35e618e501c3b19dL59-R60) [/#diff-b335630551682c19a781afebcf4d07bf978fb1f8ac04c6bf87428ed5106870f5L15-R15](https://github.com///issues/diff-b335630551682c19a781afebcf4d07bf978fb1f8ac04c6bf87428ed5106870f5L15-R15) [/#diff-b335630551682c19a781afebcf4d07bf978fb1f8ac04c6bf87428ed5106870f5L45-R57](https://github.com///issues/diff-b335630551682c19a781afebcf4d07bf978fb1f8ac04c6bf87428ed5106870f5L45-R57) [/#diff-b335630551682c19a781afebcf4d07bf978fb1f8ac04c6bf87428ed5106870f5R90-R102](https://github.com///issues/diff-b335630551682c19a781afebcf4d07bf978fb1f8ac04c6bf87428ed5106870f5R90-R102) [/#diff-b335630551682c19a781afebcf4d07bf978fb1f8ac04c6bf87428ed5106870f5R138-R175](https://github.com///issues/diff-b335630551682c19a781afebcf4d07bf978fb1f8ac04c6bf87428ed5106870f5R138-R175) [/#diff-b335630551682c19a781afebcf4d07bf978fb1f8ac04c6bf87428ed5106870f5R220-R245](https://github.com///issues/diff-b335630551682c19a781afebcf4d07bf978fb1f8ac04c6bf87428ed5106870f5R220-R245) [/#diff-b335630551682c19a781afebcf4d07bf978fb1f8ac04c6bf87428ed5106870f5R301](https://github.com///issues/diff-b335630551682c19a781afebcf4d07bf978fb1f8ac04c6bf87428ed5106870f5R301) [/#diff-0b5ca119d2be595aa307d34512d9679e49186307ef94201e4b3dfa079aa89938L7-R38](https://github.com///issues/diff-0b5ca119d2be595aa307d34512d9679e49186307ef94201e4b3dfa079aa89938L7-R38) [/#diff-a89fdf8e6256ba8002ee2b31356838c5cf6ae12869314c81c193bac8f3ea138bR144-R175](https://github.com///issues/diff-a89fdf8e6256ba8002ee2b31356838c5cf6ae12869314c81c193bac8f3ea138bR144-R175) [/#diff-a89fdf8e6256ba8002ee2b31356838c5cf6ae12869314c81c193bac8f3ea138bL183-R283](https://github.com///issues/diff-a89fdf8e6256ba8002ee2b31356838c5cf6ae12869314c81c193bac8f3ea138bL183-R283) [/#diff-fde0e5d64aae13964fdda6d47af304cf1a7015cbc17e440ac4a5e662ee1d875eR1-R98](https://github.com///issues/diff-fde0e5d64aae13964fdda6d47af304cf1a7015cbc17e440ac4a5e662ee1d875eR1-R98) [/#diff-e774e90e159e39c0a392fffa584ea8520508a9a0c10468d0bd685800e28a42f5R1-R27](https://github.com///issues/diff-e774e90e159e39c0a392fffa584ea8520508a9a0c10468d0bd685800e28a42f5R1-R27)


### Features

* Dialogs ([#3](https://github.com/AgentSmithyAI/agentsmithy-local/issues/3)) ([4a24bc2](https://github.com/AgentSmithyAI/agentsmithy-local/commit/4a24bc2785d5098d4a0b42cd741237c254e8c2b9))
* File editing tools ([#5](https://github.com/AgentSmithyAI/agentsmithy-local/issues/5)) ([6050c5f](https://github.com/AgentSmithyAI/agentsmithy-local/commit/6050c5f56c836cdfcbbcac6221b5886243e8bcb0))
* Logic actions ([#1](https://github.com/AgentSmithyAI/agentsmithy-local/issues/1)) ([a3c4d40](https://github.com/AgentSmithyAI/agentsmithy-local/commit/a3c4d406fabe2f81f210e8bf10e1128648686674))
* Project structure ([#2](https://github.com/AgentSmithyAI/agentsmithy-local/issues/2)) ([8fbd536](https://github.com/AgentSmithyAI/agentsmithy-local/commit/8fbd536ae9769a03f5c4683d42f53f59dcf63c09))
* Run command tool ([#7](https://github.com/AgentSmithyAI/agentsmithy-local/issues/7)) ([75ffc00](https://github.com/AgentSmithyAI/agentsmithy-local/commit/75ffc002fc9be7e0ec6a03150be44baf871d9e67))
* WebFetch tool ([#10](https://github.com/AgentSmithyAI/agentsmithy-local/issues/10)) ([afb33d5](https://github.com/AgentSmithyAI/agentsmithy-local/commit/afb33d5f7a622e11513da0eb7eaeb3f4c74fc476))
* WebSearch tool ([#9](https://github.com/AgentSmithyAI/agentsmithy-local/issues/9)) ([01535ff](https://github.com/AgentSmithyAI/agentsmithy-local/commit/01535ff5ebe274a56ade1e580bcf2eedcb0dc00f)), closes [/#diff-7972b59e2e307143f740c7922b1c26431b06d909cabb5ed541f143a1e350dd16R11](https://github.com///issues/diff-7972b59e2e307143f740c7922b1c26431b06d909cabb5ed541f143a1e350dd16R11) [/#diff-7972b59e2e307143f740c7922b1c26431b06d909cabb5ed541f143a1e350dd16R30](https://github.com///issues/diff-7972b59e2e307143f740c7922b1c26431b06d909cabb5ed541f143a1e350dd16R30) [/#diff-8c50118cb42b16f33d4125eacd1598f251af26a645ca8296e2e021e881581aabR24](https://github.com///issues/diff-8c50118cb42b16f33d4125eacd1598f251af26a645ca8296e2e021e881581aabR24) [/#diff-8c50118cb42b16f33d4125eacd1598f251af26a645ca8296e2e021e881581aabR97-R102](https://github.com///issues/diff-8c50118cb42b16f33d4125eacd1598f251af26a645ca8296e2e021e881581aabR97-R102) [/#diff-8c50118cb42b16f33d4125eacd1598f251af26a645ca8296e2e021e881581aabR155-R158](https://github.com///issues/diff-8c50118cb42b16f33d4125eacd1598f251af26a645ca8296e2e021e881581aabR155-R158) [/#diff-8c50118cb42b16f33d4125eacd1598f251af26a645ca8296e2e021e881581aabR186-R187](https://github.com///issues/diff-8c50118cb42b16f33d4125eacd1598f251af26a645ca8296e2e021e881581aabR186-R187) [/#diff-a47c1b7f456172aa76d31b51f5ff44e6a19614634c52bb5c83a942c50c8d023eR20](https://github.com///issues/diff-a47c1b7f456172aa76d31b51f5ff44e6a19614634c52bb5c83a942c50c8d023eR20) [/#diff-a47c1b7f456172aa76d31b51f5ff44e6a19614634c52bb5c83a942c50c8d023eR35](https://github.com///issues/diff-a47c1b7f456172aa76d31b51f5ff44e6a19614634c52bb5c83a942c50c8d023eR35) [/#diff-bdd4bc7a33a61bf0fc4a682b15a04205a3ca4c0710d6bdbc5156c66ae1b0d653R55](https://github.com///issues/diff-bdd4bc7a33a61bf0fc4a682b15a04205a3ca4c0710d6bdbc5156c66ae1b0d653R55) [/#diff-bdd4bc7a33a61bf0fc4a682b15a04205a3ca4c0710d6bdbc5156c66ae1b0d653R98-R102](https://github.com///issues/diff-bdd4bc7a33a61bf0fc4a682b15a04205a3ca4c0710d6bdbc5156c66ae1b0d653R98-R102) [/#diff-bdd4bc7a33a61bf0fc4a682b15a04205a3ca4c0710d6bdbc5156c66ae1b0d653R150-R153](https://github.com///issues/diff-bdd4bc7a33a61bf0fc4a682b15a04205a3ca4c0710d6bdbc5156c66ae1b0d653R150-R153)
