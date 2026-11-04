/* Meraki Config Manager – Web App Logic */

function app() {
  return {
    // ── Auth ──────────────────────────────────────────────────────────────────
    authenticated: false,
    csrfToken: '',
    apiKey: '',
    loginError: '',
    loginStatus: '',
    loginLoading: false,

    // ── Navigation ────────────────────────────────────────────────────────────
    page: 'dashboard',
    pageTitles: {
      dashboard: 'Dashboard', networks: 'Networks',
      exclusions: 'VPN Exclusions', copy: 'Copy Rules',
      grouppolicies: 'Group Policies',
       compare: 'Compare Networks', newnet: 'New Network',
       deviceaddr: 'Device Addresses',
        syslog: 'Syslog Servers',
        syslogcopy: 'Copy Syslog',
       activity: 'Activity Log',
    },
    pageOverviews: {
      dashboard: 'Summary of the selected organization’s MX networks and VPN exclusion rules, with shortcuts to common tasks.',
      networks: 'Browse and search the organization’s MX networks, then open a network to manage its VPN exclusions.',
      exclusions: 'View current split-tunnel exclusions, import proposed rules, review a dry run, and deploy approved changes.',
      copy: 'Copy selected VPN exclusion rules from one source network to one or more destination networks.',
      grouppolicies: 'Copy selected group policies from a source network to destination networks.',
      compare: 'Compare VPN rules, SSIDs, and appliance settings across networks to identify differences.',
      newnet: 'Create an MX network from a template and choose which configuration areas to copy.',
       deviceaddr: 'Bulk-update device site addresses and Dashboard map markers within a network.',
        syslog: 'Define syslog destinations and apply them to all or selected organization networks.',
        syslogcopy: 'Replace destination syslog configurations with a selected source network configuration.',
       activity: 'Review actions and results recorded during the current browser session.',
    },

    // ── Org / Network state ───────────────────────────────────────────────────
    orgs: [],
    selectedOrgId: '',
    networks: [],
    comparisonNetworks: [],
    networksLoading: false,

    // ── Dashboard ─────────────────────────────────────────────────────────────
    dashStats: { networkCount: 0, exclusionCount: 0, orgName: '' },
    dashLoading: false,

    // ── Networks page ─────────────────────────────────────────────────────────
    networkSearch: '',

    // ── Exclusions page ───────────────────────────────────────────────────────
    exclNetworkSearch: '',
    exclNetwork: null,
    exclCurrentRules: [],
    exclProposedRules: [],
    exclMode: 'merge',
    exclImportLoading: false,
    exclDryRunResult: null,
    exclDeployLoading: false,
    exclDeployResult: null,
    exclLoading: false,

    // ── Copy Wizard ───────────────────────────────────────────────────────────
    copyStep: 1,
    copySourceNetwork: null,
    copySourceRules: [],
    copySelectedRuleIdxs: [],
    copyDestNetworkIds: [],
    copyPreview: null,
    copyResults: null,
    copyLoading: false,
    copySourceError: '',
    copySourceSearch: '',
    copyDestSearch: '',

    // ── Group Policies Wizard ─────────────────────────────────────────────────
    gpStep: 1,
    gpSourceNetwork: null,
    gpSourcePolicies: [],
    gpSelectedPolicyIdxs: [],
    gpDestNetworkIds: [],
    gpPreview: null,
    gpResults: null,
    gpPlanId: '',
    gpOperationId: '',
    gpConflictMode: 'skip',
    gpOverwriteAcknowledged: false,
    gpRollbackResults: null,
    gpLoading: false,
    gpSourceSearch: '',
    gpDestSearch: '',

    // ── Compare ───────────────────────────────────────────────────────────────
    cmpSource: null,
    cmpTargetIds: [],
    cmpReport: null,
    cmpTab: 'vpn',
    cmpLoading: false,
    cmpSourceSearch: '',
    cmpTargetSearch: '',

    // ── New Network Wizard ────────────────────────────────────────────────────
    nnStep: 1,
    nnTemplate: null,
    nnCloneConfig: null,
    nnName: '',
    nnTimezone: 'America/Los_Angeles',
    nnNotes: '',
    nnCopyTags: true,
    nnCopyVpn: true,
    nnCopyRoutes: false,
    nnCopyL3: false,
    nnCopyL7: false,
    nnCopySSIDs: false,
    nnCopySettings: false,
    nnCopyGroupPolicies: false,
    nnSsidPsks: {},
    nnResult: null,
    nnLoading: false,
    nnTemplateSearch: '',

    // ── Device Addresses (bulk address / map marker update) ───────────────────
    daStep: 1,
    daAllNetworks: [],
    daNetwork: null,
    daNetworkSearch: '',
    daNetworksLoading: false,
    daDevices: [],
    daDevicesLoading: false,
    daSelectedSerials: [],
    daDeviceSearch: '',
    daNewAddress: '',
    daPreview: null,
    daPreviewLoading: false,
    daRunning: false,
    daResults: [],
    daDone: 0,
    daTotal: 0,
    daCurrentLabel: '',

    // ── Syslog Servers ────────────────────────────────────────────────────────
    slStep: 1, slNetworks: [], slNetworksLoading: false, slNetworkSearch: '',
    slSelectedNetworkIds: [], slServers: [{ host: '', port: 514, roles: [] }],
    slRoles: [], slRolesByNetwork: {}, slMode: 'replace', slPreview: null, slLoading: false, slResults: null,
    slCopyStep: 1, slCopyNetworks: [], slCopySource: null, slCopyDestinationIds: [], slCopySearch: '', slCopyPreview: null, slCopyResults: null, slCopyLoading: false,

    // ── Activity Log ──────────────────────────────────────────────────────────
    actLog: [],

    // =========================================================================
    // Init
    // =========================================================================
    async init() {
      try {
        const csrf = await this.api('GET', '/api/csrf');
        this.csrfToken = csrf.csrf_token;
        this.authenticated = true;
        this.orgs = await this.api('GET', '/api/orgs');
          if (this.orgs.length === 1) {
            this.selectedOrgId = this.orgs[0].id;
            await this.loadNetworks();
          }
          // Multiple orgs → leave selectedOrgId blank, user must pick
      } catch {
        this.authenticated = false;
        this.csrfToken = '';
      }
    },

    // =========================================================================
    // Auth
    // =========================================================================
    async login() {
      this.loginError = '';
      this.loginStatus = 'Validating API key with Meraki. This takes up to 15 seconds.';
      this.loginLoading = true;
      try {
        const res = await this.api('POST', '/api/login', { api_key: this.apiKey }, 20000);
        this.apiKey = '';
        this.authenticated = true;
        this.csrfToken = res.csrf_token;
        this.orgs = res.orgs;
        if (this.orgs.length === 1) {
          // Only one org — auto-select and load
          this.selectedOrgId = this.orgs[0].id;
          await this.loadNetworks();
          await this.loadDashboard();
        }
        // Multiple orgs → user must choose from the dropdown
        this.log('Logged in successfully.', 'success');
      } catch (e) {
        this.loginError = e.message;
        this.apiKey = '';
      } finally {
        this.loginStatus = '';
        this.loginLoading = false;
      }
    },

    async logout() {
      await this.api('POST', '/api/logout').catch(() => {});
      this.authenticated = false;
      this.csrfToken = '';
      // Reset ALL state so nothing leaks into the next session
      this.orgs = []; this.networks = []; this.selectedOrgId = ''; this.page = 'dashboard';
      this.exclNetwork = null; this.exclCurrentRules = []; this.exclProposedRules = [];
      this.exclDryRunResult = null; this.exclDeployResult = null; this.exclNetworkSearch = '';
      this.copyStep = 1; this.copySourceNetwork = null; this.copySourceRules = [];
      this.copySelectedRuleIdxs = []; this.copyDestNetworkIds = [];
      this.copyPreview = null; this.copyResults = null;
      this.gpStep = 1; this.gpSourceNetwork = null; this.gpSourcePolicies = [];
      this.gpSelectedPolicyIdxs = []; this.gpDestNetworkIds = [];
      this.gpPreview = null; this.gpResults = null;
      this.gpPlanId = ''; this.gpOperationId = ''; this.gpConflictMode = 'skip';
      this.gpOverwriteAcknowledged = false; this.gpRollbackResults = null;
      this.cmpSource = null; this.cmpTargetIds = []; this.cmpReport = null;
      this.nnStep = 1; this.nnTemplate = null; this.nnCloneConfig = null; this.nnResult = null;
       this.resetDeviceAddrState(); this.daAllNetworks = [];
       this.resetSyslogState();
       this.actLog = [];
    },

    // =========================================================================
    // Networks / Orgs
    // =========================================================================
    async loadNetworks() {
      if (!this.selectedOrgId) return;
      this.networksLoading = true;
      try {
        this.networks = await this.api('GET', `/api/networks?org_id=${this.selectedOrgId}`);
        this.log(`Loaded ${this.networks.length} network(s).`, 'info');
      } catch (e) {
        this.log(`Load networks failed: ${e.message}`, 'error');
      } finally {
        this.networksLoading = false;
      }
    },

    async onOrgChange() {
      this.networks = [];
      // Clear all network-specific wizard states when org changes
      this.exclNetwork = null; this.exclCurrentRules = []; this.exclProposedRules = [];
      this.exclDryRunResult = null; this.exclDeployResult = null;
      this.copyStep = 1; this.copySourceNetwork = null; this.copySourceRules = [];
      this.copySelectedRuleIdxs = []; this.copyDestNetworkIds = [];
      this.gpStep = 1; this.gpSourceNetwork = null; this.gpSourcePolicies = [];
      this.gpSelectedPolicyIdxs = []; this.gpDestNetworkIds = [];
      this.cmpSource = null; this.cmpTargetIds = []; this.cmpReport = null;
      this.nnStep = 1; this.nnTemplate = null; this.nnCloneConfig = null;
       this.resetDeviceAddrState(); this.daAllNetworks = [];
       this.resetSyslogState();
       await this.loadNetworks();
      this.loadDashboard(); // fire without await — updates stats in background
    },

    get filteredNetworks() {
      const q = this.networkSearch.toLowerCase();
      return this.networks.filter(n =>
        !q || n.name.toLowerCase().includes(q) || (n.tags || []).join(' ').toLowerCase().includes(q)
      );
    },

    get filteredExclNetworks() {
      const q = this.exclNetworkSearch.toLowerCase();
      return this.networks.filter(n => !q || n.name.toLowerCase().includes(q));
    },

    get filteredCopySourceNetworks() {
      const q = this.copySourceSearch.toLowerCase();
      return this.networks.filter(n => !q || n.name.toLowerCase().includes(q));
    },

    get filteredCopyDestNetworks() {
      const q = this.copyDestSearch.toLowerCase();
      return this.networks.filter(n =>
        n.id !== this.copySourceNetwork?.id &&
        (!q || n.name.toLowerCase().includes(q))
      );
    },

    get filteredCmpSourceNetworks() {
      const q = this.cmpSourceSearch.toLowerCase();
      return this.comparisonNetworks.filter(n => !q || n.name.toLowerCase().includes(q));
    },

    get filteredCmpTargetNetworks() {
      const q = this.cmpTargetSearch.toLowerCase();
      return this.comparisonNetworks.filter(n =>
        n.id !== this.cmpSource?.id &&
        (!q || n.name.toLowerCase().includes(q))
      );
    },

    get filteredNnTemplateNetworks() {
      const q = this.nnTemplateSearch.toLowerCase();
      return this.networks.filter(n => !q || n.name.toLowerCase().includes(q));
    },

    get filteredGpSourceNetworks() {
      const q = this.gpSourceSearch.toLowerCase();
      return this.networks.filter(n => !q || n.name.toLowerCase().includes(q));
    },

    get filteredGpDestNetworks() {
      const q = this.gpDestSearch.toLowerCase();
      return this.networks.filter(n =>
        n.id !== this.gpSourceNetwork?.id &&
        (!q || n.name.toLowerCase().includes(q))
      );
    },

    get gpSelectedPolicies() {
      return this.gpSelectedPolicyIdxs.map(i => this.gpSourcePolicies[i]).filter(Boolean);
    },

    // =========================================================================
    // Syslog Servers
    // =========================================================================
    resetSyslogState() {
      this.slStep = 1; this.slNetworks = []; this.slNetworkSearch = '';
      this.slSelectedNetworkIds = []; this.slServers = [{ host: '', port: 514, roles: [] }];
      this.slRoles = []; this.slRolesByNetwork = {}; this.slMode = 'replace'; this.slPreview = null; this.slLoading = false; this.slResults = null;
    },
    async startSyslogWizard() {
      this.resetSyslogState(); this.page = 'syslog';
      if (!this.selectedOrgId) return;
      this.slNetworksLoading = true;
      try {
        const [networks, roleCatalog] = await Promise.all([
          this.api('GET', `/api/syslog/networks?org_id=${this.selectedOrgId}`),
          this.api('GET', `/api/syslog/roles?org_id=${this.selectedOrgId}`),
        ]);
        this.slNetworks = networks; this.slRoles = roleCatalog.roles || []; this.slRolesByNetwork = roleCatalog.by_network || {};
        this.log(`Loaded ${networks.length} network(s) for syslog configuration.`, 'info');
      } catch (e) { this.log(`Failed to load syslog setup: ${e.message}`, 'error'); }
      finally { this.slNetworksLoading = false; }
    },
    get slFilteredNetworks() {
      const q = this.slNetworkSearch.toLowerCase();
      return this.slNetworks.filter(n => !q || [n.name, ...(n.tags || [])].join(' ').toLowerCase().includes(q));
    },
    get slSelectedNetworks() { return this.slNetworks.filter(n => this.slSelectedNetworkIds.includes(n.id)); },
    get slAvailableRoles() {
      if (!this.slSelectedNetworkIds.length) return this.slRoles;
      return this.slRoles.filter(role => this.slSelectedNetworkIds.every(id => (this.slRolesByNetwork[id] || []).includes(role.value)));
    },
    slRestrictRoles() {
      const allowed = new Set(this.slAvailableRoles.map(role => role.value));
      this.slServers.forEach(server => { server.roles = server.roles.filter(role => allowed.has(role)); });
    },
    slToggleNetwork(id) { const i = this.slSelectedNetworkIds.indexOf(id); if (i >= 0) this.slSelectedNetworkIds.splice(i, 1); else this.slSelectedNetworkIds.push(id); this.slRestrictRoles(); this.slPreview = null; },
    slSelectAll() { this.slSelectedNetworkIds = [...new Set([...this.slSelectedNetworkIds, ...this.slFilteredNetworks.map(n => n.id)])]; this.slPreview = null; },
    slDeselectAll() { const visible = new Set(this.slFilteredNetworks.map(n => n.id)); this.slSelectedNetworkIds = this.slSelectedNetworkIds.filter(id => !visible.has(id)); this.slPreview = null; },
    slAddServer() { this.slServers.push({ host: '', port: 514, roles: [] }); this.slPreview = null; },
    slRemoveServer(index) { if (this.slServers.length > 1) this.slServers.splice(index, 1); this.slPreview = null; },
    slInvalidatePreview() { this.slPreview = null; },
    async slRunPreview() {
      if (!this.slSelectedNetworks.length) return;
      this.slLoading = true;
      try { this.slPreview = await this.api('POST', '/api/syslog/preview', { networks: this.slSelectedNetworks, servers: this.slServers, mode: this.slMode }); this.slStep = 3; }
      catch (e) { this.log(`Syslog preview failed: ${e.message}`, 'error'); }
      finally { this.slLoading = false; }
    },
    async slExecute() {
      if (!this.slPreview || this.slLoading) return;
      const updates = this.slPreview.filter(p => p.status === 'update').length;
      if (!confirm(`Apply the syslog configuration to ${this.slSelectedNetworks.length} network(s)?\n\nMode: ${this.slMode === 'replace' ? 'Replace all existing servers' : 'Add or update entered servers'}\n${updates} network(s) will be changed.`)) return;
      this.slLoading = true;
      try {
        this.slResults = await this.api('POST', '/api/syslog/execute', { networks: this.slSelectedNetworks, servers: this.slServers, mode: this.slMode });
        this.slStep = 4;
        const updated = this.slResults.filter(r => r.status === 'updated').length;
        const failed = this.slResults.filter(r => !r.success).length;
        this.log(`Syslog update complete: ${updated} updated, ${failed} failed.`, failed ? 'warning' : 'success');
      } catch (e) { this.log(`Syslog update failed: ${e.message}`, 'error'); }
      finally { this.slLoading = false; }
    },
    slServerLabel(server) { return `${server.host}:${server.port} — ${(server.roles || []).join(', ')}`; },
    async startSyslogCopy() {
      this.page = 'syslogcopy'; this.slCopyStep = 1; this.slCopySource = null; this.slCopyDestinationIds = []; this.slCopySearch = ''; this.slCopyPreview = null; this.slCopyResults = null;
      // Reuse the organization networks already loaded at sign-in. This avoids
      // a redundant Meraki request when opening the copy wizard.
      if (!this.networks.length && this.selectedOrgId) await this.loadNetworks();
      this.slCopyNetworks = [...this.networks];
    },
    get slCopyFilteredNetworks() { const q = this.slCopySearch.toLowerCase(); return this.slCopyNetworks.filter(n => !q || [n.name, ...(n.tags || [])].join(' ').toLowerCase().includes(q)); },
    get slCopyDestinations() { return this.slCopyNetworks.filter(n => this.slCopyDestinationIds.includes(n.id) && n.id !== this.slCopySource?.id); },
    slCopyToggleDestination(id) { const i = this.slCopyDestinationIds.indexOf(id); if (i >= 0) this.slCopyDestinationIds.splice(i, 1); else this.slCopyDestinationIds.push(id); this.slCopyPreview = null; },
    slCopySelectAllVisible() { this.slCopyDestinationIds = [...new Set([...this.slCopyDestinationIds, ...this.slCopyFilteredNetworks.filter(n => n.id !== this.slCopySource?.id).map(n => n.id)])]; this.slCopyPreview = null; },
    slCopyDeselectAllVisible() { const visible = new Set(this.slCopyFilteredNetworks.map(n => n.id)); this.slCopyDestinationIds = this.slCopyDestinationIds.filter(id => !visible.has(id)); this.slCopyPreview = null; },
    async slCopyRunPreview() {
      if (!this.slCopySource || !this.slCopyDestinations.length) return;
      this.slCopyLoading = true;
      try { this.slCopyPreview = await this.api('POST', '/api/syslog/copy/preview', { org_id: this.selectedOrgId, source: this.slCopySource, destinations: this.slCopyDestinations }); this.slCopyStep = 3; }
      catch (e) { this.log(`Syslog copy preview failed: ${e.message}`, 'error'); }
      finally { this.slCopyLoading = false; }
    },
    async slCopyExecute() {
      const updates = (this.slCopyPreview || []).filter(p => p.status === 'update').length;
      if (!updates || !confirm(`Replace syslog configuration on ${updates} compatible network(s) with ${this.slCopySource.name}?`)) return;
      this.slCopyLoading = true;
      try { this.slCopyResults = await this.api('POST', '/api/syslog/copy/execute', { org_id: this.selectedOrgId, source: this.slCopySource, destinations: this.slCopyDestinations }); this.slCopyStep = 4; }
      catch (e) { this.log(`Syslog copy failed: ${e.message}`, 'error'); }
      finally { this.slCopyLoading = false; }
    },

    get gpDestNetworks() {
      return this.networks.filter(n =>
        this.gpDestNetworkIds.includes(n.id) && n.id !== this.gpSourceNetwork?.id
      );
    },

    selectedOrg() {
      return this.orgs.find(o => o.id === this.selectedOrgId) || null;
    },

    // =========================================================================
    // Dashboard
    // =========================================================================
    async loadDashboard() {
      this.dashLoading = true;
      // Fetching exclusions for every network at login creates a large burst of
      // Meraki API calls. For large organizations that triggers rate limiting
      // and delays every other tool, including Syslog Servers. VPN rule counts
      // remain available when a user opens an individual network.
      this.dashStats = {
        networkCount: this.networks.length,
        exclusionCount: 'Open a network to view',
        orgName: this.selectedOrg()?.name || '',
      };
      this.dashLoading = false;
    },

    // =========================================================================
    // VPN Exclusions
    // =========================================================================
    async loadExclusions(network) {
      this.exclNetwork = network;
      this.exclCurrentRules = [];
      this.exclProposedRules = [];
      this.exclDryRunResult = null;
      this.exclDeployResult = null;
      this.exclLoading = true;
      this.page = 'exclusions';
      try {
        const rs = await this.api('GET', `/api/exclusions?org_id=${this.selectedOrgId}&network_id=${network.id}`);
        this.exclCurrentRules = rs.rules;
        this.log(`Loaded ${rs.rules.length} VPN rule(s) for ${network.name}.`, 'info');
      } catch (e) {
        this.log(`Failed to load rules: ${e.message}`, 'error');
      } finally {
        this.exclLoading = false;
      }
    },

    async importFile(event) {
      const file = event.target.files[0];
      if (!file) return;
      this.exclImportLoading = true;
      try {
        const fd = new FormData();
        fd.append('file', file);
        const rs = await this.apiForm('/api/exclusions/import', fd);
        this.exclProposedRules = rs.rules;
        this.exclMode = rs.mode || 'merge';
        this.exclDryRunResult = null;
        this.log(`Imported ${rs.rules.length} rule(s) from ${file.name}.`, 'success');
      } catch (e) {
        this.log(`Import failed: ${e.message}`, 'error');
      } finally {
        this.exclImportLoading = false;
        event.target.value = '';
      }
    },

    async runDryRun() {
      if (!this.exclNetwork || !this.exclProposedRules.length) return;
      this.exclLoading = true;
      this.exclDryRunResult = null;
      try {
        this.exclDryRunResult = await this.api('POST', '/api/exclusions/dry-run', {
          org_id: this.selectedOrgId,
          network_id: this.exclNetwork.id,
          network_name: this.exclNetwork.name,
          proposed_rules: this.exclProposedRules,
          mode: this.exclMode,
        });
        this.log(`Dry run: ${this.exclDryRunResult.change_count} change(s) for ${this.exclNetwork.name}.`, 'info');
      } catch (e) {
        this.log(`Dry run failed: ${e.message}`, 'error');
      } finally {
        this.exclLoading = false;
      }
    },

    async deployRules() {
      if (!this.exclDryRunResult || this.exclDryRunResult.has_blockers) return;
      if (!confirm(`Deploy ${this.exclDryRunResult.change_count} change(s) to ${this.exclNetwork.name}?`)) return;
      this.exclDeployLoading = true;
      this.exclDeployResult = null;
      try {
        await this.api('POST', '/api/exclusions/deploy', { network_id: this.exclNetwork.id });
        this.exclDeployResult = { ok: true };
        this.log(`Deployed successfully to ${this.exclNetwork.name}.`, 'success');
        this.exclDryRunResult = null;
        await this.loadExclusions(this.exclNetwork);
      } catch (e) {
        this.exclDeployResult = { ok: false, error: e.message };
        this.log(`Deploy failed: ${e.message}`, 'error');
      } finally {
        this.exclDeployLoading = false;
      }
    },

    changeClass(kind) {
      return { new: 'change-new', removed: 'change-removed', unchanged: 'change-unchanged', duplicate: 'change-duplicate', invalid: 'change-invalid' }[kind] || '';
    },

    changeIcon(kind) {
      return { new: '＋', removed: '−', unchanged: '=', duplicate: '⚠', invalid: '✗' }[kind] || '?';
    },

    // =========================================================================
    // Copy Wizard
    // =========================================================================
    startCopyWizard() {
      this.copyStep = 1; this.copySourceNetwork = null; this.copySourceRules = [];
      this.copySelectedRuleIdxs = []; this.copyDestNetworkIds = [];
      this.copyPreview = null; this.copyResults = null;
      this.copySourceSearch = ''; this.copyDestSearch = ''; this.copySourceError = '';
      this.page = 'copy';
    },

    async copySelectSource(network) {
      this.copySourceError = '';
      this.copySourceNetwork = network;
      this.copyLoading = true;
      try {
        const rs = await this.api('GET', `/api/exclusions?org_id=${this.selectedOrgId}&network_id=${network.id}`);
        this.copySourceRules = rs.rules;
        this.copySelectedRuleIdxs = rs.rules.map((_, i) => i);
        this.copyStep = 2;
      } catch (e) {
        this.copySourceNetwork = null;
        this.copySourceError = `Could not load VPN rules from ${network.name}: ${e.message}`;
        this.log(`Failed to load rules: ${e.message}`, 'error');
      } finally {
        this.copyLoading = false;
      }
    },

    toggleCopyRule(i) {
      const idx = this.copySelectedRuleIdxs.indexOf(i);
      if (idx >= 0) this.copySelectedRuleIdxs.splice(idx, 1);
      else this.copySelectedRuleIdxs.push(i);
    },

    toggleCopyDest(id) {
      const idx = this.copyDestNetworkIds.indexOf(id);
      if (idx >= 0) this.copyDestNetworkIds.splice(idx, 1);
      else this.copyDestNetworkIds.push(id);
    },

    get copySelectedRules() {
      return this.copySelectedRuleIdxs.map(i => this.copySourceRules[i]).filter(Boolean);
    },

    get copyDestNetworks() {
      return this.networks.filter(n => this.copyDestNetworkIds.includes(n.id) && n.id !== this.copySourceNetwork?.id);
    },

    async runCopyPreview() {
      if (!this.copySelectedRules.length || !this.copyDestNetworks.length) return;
      this.copyLoading = true;
      try {
        this.copyPreview = await this.api('POST', '/api/copy/preview', {
          org_id: this.selectedOrgId,
          selected_rules: this.copySelectedRules,
          destination_networks: this.copyDestNetworks,
        });
        this.copyStep = 4;
      } catch (e) {
        this.log(`Preview failed: ${e.message}`, 'error');
      } finally {
        this.copyLoading = false;
      }
    },

    async runCopyExecute() {
      if (!confirm(`Copy ${this.copySelectedRules.length} rule(s) to ${this.copyDestNetworks.length} network(s)?`)) return;
      this.copyLoading = true;
      try {
        this.copyResults = await this.api('POST', '/api/copy/execute', {
          org_id: this.selectedOrgId,
          selected_rules: this.copySelectedRules,
          destination_networks: this.copyDestNetworks,
        });
        this.copyStep = 5;
        const added = this.copyResults.reduce((s, r) => s + r.rules_added, 0);
        this.log(`Copy complete: ${added} rule(s) added across ${this.copyResults.length} network(s).`, 'success');
      } catch (e) {
        this.log(`Copy failed: ${e.message}`, 'error');
      } finally {
        this.copyLoading = false;
      }
    },

    ruleLabel(rule) {
      if (rule.destination) return `${rule.protocol} → ${rule.destination}:${rule.port}`;
      if (rule.name) return rule.name;
      if (rule.application_id) return rule.application_id;
      return '—';
    },

    // =========================================================================
    // Group Policies Wizard
    // =========================================================================
    startGpWizard() {
      this.gpStep = 1; this.gpSourceNetwork = null; this.gpSourcePolicies = [];
      this.gpSelectedPolicyIdxs = []; this.gpDestNetworkIds = [];
      this.gpPreview = null; this.gpResults = null;
      this.gpSourceSearch = ''; this.gpDestSearch = '';
      this.page = 'grouppolicies';
    },

    async gpSelectSource(network) {
      this.gpSourceNetwork = network;
      this.gpLoading = true;
      try {
        const policies = await this.api('GET', `/api/group-policies?network_id=${network.id}`);
        this.gpSourcePolicies = policies;
        this.gpSelectedPolicyIdxs = policies.map((_, i) => i);
        this.gpStep = 2;
        this.log(`Loaded ${policies.length} group policy/policies from ${network.name}.`, 'info');
      } catch (e) {
        this.log(`Failed to load group policies: ${e.message}`, 'error');
      } finally {
        this.gpLoading = false;
      }
    },

    toggleGpPolicy(i) {
      const idx = this.gpSelectedPolicyIdxs.indexOf(i);
      if (idx >= 0) this.gpSelectedPolicyIdxs.splice(idx, 1);
      else this.gpSelectedPolicyIdxs.push(i);
    },

    toggleGpDest(id) {
      const idx = this.gpDestNetworkIds.indexOf(id);
      if (idx >= 0) this.gpDestNetworkIds.splice(idx, 1);
      else this.gpDestNetworkIds.push(id);
    },

    gpPolicySummary(policy) {
      const bw = policy.bandwidth?.settings || 'network default';
      const vlan = policy.vlanTagging?.settings || 'network default';
      const fw = policy.firewallAndTrafficShaping?.settings || 'network default';
      return `bw: ${bw}  |  vlan: ${vlan}  |  fw: ${fw}`;
    },

    async runGpPreview() {
      if (!this.gpSelectedPolicies.length || !this.gpDestNetworks.length) return;
      this.gpOverwriteAcknowledged = false;
      this.gpLoading = true;
      try {
        this.gpPreview = await this.api('POST', '/api/group-policies/dry-run', {
          source_network_id: this.gpSourceNetwork.id,
          selected_policy_ids: this.gpSelectedPolicies.map(p => p.groupPolicyId),
          destination_network_ids: this.gpDestNetworkIds,
          conflict_mode: this.gpConflictMode,
        });
        this.gpPlanId = this.gpPreview.plan_id;
        this.gpStep = 4;
      } catch (e) {
        this.log(`Group policy preview failed: ${e.message}`, 'error');
      } finally {
        this.gpLoading = false;
      }
    },

    async runGpExecute() {
      const overwrites = this.gpPreview.items.filter(i => i.action === 'overwrite').length;
      if (overwrites && !this.gpOverwriteAcknowledged) return;
      const prompt = overwrites
        ? `Overwrite ${overwrites} existing policy configuration(s)? This replaces all writable settings and rules. Rollback is only available during this active session.`
        : `Apply this reviewed dry run to ${this.gpDestNetworks.length} network(s)?`;
      if (!confirm(prompt)) return;
      this.gpLoading = true;
      try {
        const operation = await this.api('POST', '/api/group-policies/execute', {
          plan_id: this.gpPlanId,
          allow_overwrite: this.gpOverwriteAcknowledged,
        });
        this.gpOperationId = operation.operation_id;
        this.gpResults = operation.results;
        this.gpStep = 5;
        const added = this.gpResults.filter(r => r.action === 'missing' && r.success).length;
        this.log(
          `Group policy copy complete: ${added} missing policy/policies added across ` +
          `${this.gpResults.length} network(s).`, 'success'
        );
      } catch (e) {
        this.log(`Group policy copy failed: ${e.message}`, 'error');
      } finally {
        this.gpLoading = false;
      }
    },

    async runGpRollback() {
      if (!this.gpOperationId || !confirm('Roll back this session\'s completed Group Policy changes?')) return;
      this.gpLoading = true;
      try {
        const result = await this.api('POST', '/api/group-policies/rollback', {
          operation_id: this.gpOperationId,
        });
        this.gpRollbackResults = result.results;
        this.log('Group Policy rollback finished. Review the results below.', 'info');
      } catch (e) {
        this.log(`Group Policy rollback failed: ${e.message}`, 'error');
      } finally {
        this.gpLoading = false;
      }
    },

    // =========================================================================
    // Compare Networks
    // =========================================================================
    async startCompare() {
      this.cmpSource = null; this.cmpTargetIds = []; this.cmpReport = null; this.cmpTab = 'vpn';
      this.cmpSourceSearch = ''; this.cmpTargetSearch = '';
      this.page = 'compare';
      try {
        this.comparisonNetworks = await this.api('GET', `/api/comparison-networks?org_id=${this.selectedOrgId}`);
      } catch (e) {
        this.log(`Could not load networks for comparison: ${e.message}`, 'error');
      }
    },

    toggleCmpTarget(id) {
      const idx = this.cmpTargetIds.indexOf(id);
      if (idx >= 0) this.cmpTargetIds.splice(idx, 1);
      else this.cmpTargetIds.push(id);
    },

    get cmpTargetNetworks() {
      return this.comparisonNetworks.filter(n => this.cmpTargetIds.includes(n.id) && n.id !== this.cmpSource?.id);
    },

    async runCompare() {
      if (!this.cmpSource || !this.cmpTargetNetworks.length) return;
      this.cmpLoading = true; this.cmpReport = null;
      try {
        this.cmpReport = await this.api('POST', '/api/compare', {
          org_id: this.selectedOrgId,
          source_network: this.cmpSource,
          target_networks: this.cmpTargetNetworks,
        });
        this.log(`Compare complete: ${this.cmpReport.vpn_rules.length} VPN rule(s) compared.`, 'info');
      } catch (e) {
        this.log(`Compare failed: ${e.message}`, 'error');
      } finally {
        this.cmpLoading = false;
      }
    },

    cellClass(cell) {
      return { match: 'compare-match', missing: 'compare-missing', different: 'compare-different', na: 'compare-na' }[cell?.status] || '';
    },

    cellIcon(cell) {
      return { match: '✓', missing: '✗', different: '!', na: '—' }[cell?.status] || '?';
    },

    cellDetail(cell) {
      if (!cell) return '';
      if (cell.status === 'match') return '';
      if (cell.status === 'missing') return 'Missing';
      if (cell.status === 'different') return cell.detail || 'Extra';
      if (cell.status === 'na') return '';
      return cell.detail || '';
    },

    // =========================================================================
    // New Network Wizard
    // =========================================================================
    startNewNet() {
      this.nnStep = 1; this.nnTemplate = null; this.nnCloneConfig = null;
      this.nnName = ''; this.nnNotes = ''; this.nnSsidPsks = {};
      this.nnCopyTags = true; this.nnCopyVpn = true; this.nnCopyRoutes = false;
      this.nnCopyL3 = false; this.nnCopyL7 = false; this.nnCopySSIDs = false;
      this.nnCopySettings = false; this.nnCopyGroupPolicies = false;
      this.nnResult = null; this.nnTemplateSearch = '';
      this.page = 'newnet';
    },

    async nnSelectTemplate(network) {
      this.nnTemplate = network;
      this.nnLoading = true;
      this.nnTimezone = 'America/Los_Angeles';
      try {
        this.nnCloneConfig = await this.api('POST', '/api/network/clone-config', {
          org_id: this.selectedOrgId,
          source_network: network,
        });
        this.nnTimezone = this.nnCloneConfig.source_timezone || 'America/Los_Angeles';
        this.nnStep = 2;
      } catch (e) {
        this.log(`Failed to read template: ${e.message}`, 'error');
      } finally {
        this.nnLoading = false;
      }
    },

    get nnPskSsids() {
      if (!this.nnCloneConfig || !this.nnCopySSIDs) return [];
      return (this.nnCloneConfig.ssids || []).filter(s => s.authMode === 'psk' && s.enabled);
    },

    async nnCreate() {
      if (!this.nnName.trim()) { alert('Enter a network name.'); return; }
      if (!confirm(`Create network "${this.nnName}"?`)) return;
      this.nnLoading = true; this.nnResult = null;
      try {
        this.nnResult = await this.api('POST', '/api/network/create', {
          org_id: this.selectedOrgId,
          source_network_id: this.nnTemplate.id,
          name: this.nnName,
          timezone: this.nnTimezone,
          notes: this.nnNotes,
          copy_tags: this.nnCopyTags,
          copy_vpn_exclusions: this.nnCopyVpn,
          copy_static_routes: this.nnCopyRoutes,
          copy_l3_firewall: this.nnCopyL3,
          copy_l7_firewall: this.nnCopyL7,
          copy_ssids: this.nnCopySSIDs,
          copy_network_settings: this.nnCopySettings,
          copy_group_policies: this.nnCopyGroupPolicies,
          ssid_psks: this.nnSsidPsks,
        });
        this.nnStep = 6;
        if (this.nnResult.success) {
          this.log(`Network "${this.nnResult.network_name}" created successfully.`, 'success');
          await this.loadNetworks();
        } else {
          this.log(`Network creation failed: ${this.nnResult.error}`, 'error');
        }
      } catch (e) {
        this.log(`Create failed: ${e.message}`, 'error');
      } finally {
        this.nnLoading = false;
      }
    },

    // =========================================================================
    // Device Addresses — bulk address / map marker update
    // =========================================================================
    resetDeviceAddrState() {
      this.daStep = 1;
      this.daNetwork = null; this.daNetworkSearch = '';
      this.daDevices = []; this.daSelectedSerials = []; this.daDeviceSearch = '';
      this.daNewAddress = ''; this.daPreview = null;
      this.daRunning = false; this.daResults = [];
      this.daDone = 0; this.daTotal = 0; this.daCurrentLabel = '';
    },

    startDeviceAddrWizard() {
      if (this.daRunning) { this.page = 'deviceaddr'; return; }
      this.resetDeviceAddrState();
      this.page = 'deviceaddr';
      this.loadAllNetworks();
    },

    // Devices needing an address are often APs/switches/cameras, so this uses
    // the unfiltered network list rather than the appliance-only one.
    async loadAllNetworks() {
      if (!this.selectedOrgId) return;
      this.daNetworksLoading = true;
      try {
        this.daAllNetworks = await this.api('GET', `/api/all-networks?org_id=${this.selectedOrgId}`);
      } catch (e) {
        this.log(`Load networks failed: ${e.message}`, 'error');
      } finally {
        this.daNetworksLoading = false;
      }
    },

    get daFilteredNetworks() {
      const q = this.daNetworkSearch.toLowerCase();
      return this.daAllNetworks.filter(n => !q || (n.name || '').toLowerCase().includes(q));
    },

    async daSelectNetwork(network) {
      this.daNetwork = network;
      this.daDevices = []; this.daSelectedSerials = []; this.daDeviceSearch = '';
      this.daPreview = null; this.daNewAddress = '';
      this.daDevicesLoading = true;
      try {
        this.daDevices = await this.api('GET', `/api/devices?network_id=${network.id}`);
        this.daStep = 2;
        this.log(`Loaded ${this.daDevices.length} device(s) from ${network.name}.`, 'info');
        if (!this.daDevices.length) {
          this.log(`${network.name} has no devices to update.`, 'warning');
        }
      } catch (e) {
        this.log(`Failed to load devices: ${e.message}`, 'error');
      } finally {
        this.daDevicesLoading = false;
      }
    },

    daLabel(d) {
      return (d.name || '').trim() || (d.mac || '').trim() || (d.serial || '').trim() || '(unnamed device)';
    },

    daCoord(v) {
      return (v === null || v === undefined) ? '—' : Number(v).toFixed(6);
    },

    get daFilteredDevices() {
      const q = this.daDeviceSearch.toLowerCase();
      if (!q) return this.daDevices;
      return this.daDevices.filter(d =>
        [this.daLabel(d), d.model, d.serial, d.address].join(' ').toLowerCase().includes(q)
      );
    },

    daToggleDevice(serial) {
      const i = this.daSelectedSerials.indexOf(serial);
      if (i >= 0) this.daSelectedSerials.splice(i, 1);
      else this.daSelectedSerials.push(serial);
      this.daPreview = null;   // selection changed → previous preview is stale
    },

    // Select All applies to the currently visible (filtered) rows; individual
    // devices can still be unticked afterwards.
    daSelectAll() {
      const visible = this.daFilteredDevices.map(d => d.serial);
      this.daSelectedSerials = [...new Set([...this.daSelectedSerials, ...visible])];
      this.daPreview = null;
    },

    daDeselectAll() {
      const visible = new Set(this.daFilteredDevices.map(d => d.serial));
      this.daSelectedSerials = this.daSelectedSerials.filter(s => !visible.has(s));
      this.daPreview = null;
    },

    get daSelectedDevices() {
      return this.daDevices.filter(d => this.daSelectedSerials.includes(d.serial));
    },

    daGoToAddress() {
      if (!this.daSelectedDevices.length) return;
      this.daPreview = null;
      this.daStep = 3;
    },

    async daRunPreview() {
      const address = this.daNewAddress.trim();
      if (!address || !this.daSelectedDevices.length) return;
      this.daPreviewLoading = true;
      try {
        this.daPreview = await this.api('POST', '/api/devices/address/preview', {
          devices: this.daSelectedDevices,
          new_address: address,
        });
      } catch (e) {
        this.daPreview = null;
        this.log(`Preview failed: ${e.message}`, 'error');
      } finally {
        this.daPreviewLoading = false;
      }
    },

    // Devices are updated one request at a time so progress is live and a
    // failure on any single device never stops the remaining ones.
    async daExecute() {
      if (!this.daPreview || this.daRunning) return;
      const devices = this.daSelectedDevices;
      const address = this.daPreview.new_address;
      const ok = confirm(
        `Apply the address\n\n    ${address}\n\n` +
        `to ${devices.length} selected device(s)?\n\n` +
        `• ${this.daPreview.change_count} address change(s)\n` +
        `• ${this.daPreview.remap_count} device(s) with the right address but no map marker\n` +
        `• ${this.daPreview.unchanged_count} already correct\n\n` +
        `Each device's map marker on the Meraki Dashboard will be moved to match ` +
        `the new address. No other device settings are modified.`
      );
      if (!ok) return;

      this.daRunning = true;
      this.daResults = [];
      this.daDone = 0;
      this.daTotal = devices.length;
      this.daCurrentLabel = '';
      this.daStep = 4;
      this.log(`Bulk address update started: ${devices.length} device(s) → ${address}`, 'info');

      for (const device of devices) {
        this.daCurrentLabel = this.daLabel(device);
        try {
          const res = await this.api('POST', '/api/devices/address/update-one', {
            device, new_address: address,
          });
          this.daResults.push(res);
        } catch (e) {
          // Transport/session error — record it and keep going.
          this.daResults.push({
            serial: device.serial, name: this.daLabel(device), model: device.model || '',
            success: false, old_address: device.address || '', new_address: address,
            lat: null, lng: null, verified: false, verify_note: '', error: e.message,
          });
        }
        this.daDone += 1;
      }

      this.daRunning = false;
      this.daCurrentLabel = '';
      const failed = this.daFailedCount;
      this.log(
        `Bulk address update complete: ${this.daSuccessCount} updated, ${failed} failed ` +
        `(${this.daVerifiedCount} verified on dashboard).`,
        failed === 0 ? 'success' : 'warning'
      );
    },

    get daSuccessCount() { return this.daResults.filter(r => r.success).length; },
    get daFailedCount()  { return this.daResults.filter(r => !r.success).length; },
    get daVerifiedCount() { return this.daResults.filter(r => r.success && r.verified).length; },
    get daProgressPct() {
      return this.daTotal ? Math.round((this.daDone / this.daTotal) * 100) : 0;
    },

    // =========================================================================
    // Activity Log
    // =========================================================================
    log(msg, level = 'info') {
      const time = new Date().toLocaleTimeString();
      this.actLog.unshift({ time, msg, level });
      if (this.actLog.length > 200) this.actLog.pop();
    },

    // =========================================================================
    // API helpers
    // =========================================================================
    async api(method, path, body, timeoutMs = 30000) {
      const controller = new AbortController();
      const timeout = setTimeout(() => controller.abort(), timeoutMs);
      const opts = {
        method,
        credentials: 'same-origin',
        headers: {},
        signal: controller.signal,
      };
      if (!['GET', 'HEAD', 'OPTIONS'].includes(method)) opts.headers['X-CSRF-Token'] = this.csrfToken;
      if (body) {
        opts.headers['Content-Type'] = 'application/json';
        opts.body = JSON.stringify(body);
      }
      try {
        const res = await fetch(path, opts);
        if (!res.ok) {
          const err = await res.json().catch(() => ({ detail: res.statusText }));
          throw new Error(err.detail || 'Request failed');
        }
        return res.json();
      } catch (error) {
        if (error.name === 'AbortError') throw new Error('Login timed out. Check your internet connection, proxy/VPN, firewall, and access to api.meraki.com.');
        throw error;
      } finally {
        clearTimeout(timeout);
      }
    },

    async apiForm(path, formData) {
      const res = await fetch(path, {
        method: 'POST',
        credentials: 'same-origin',
        headers: { 'X-CSRF-Token': this.csrfToken },
        body: formData,
      });
      if (!res.ok) {
        const err = await res.json().catch(() => ({ detail: res.statusText }));
        throw new Error(err.detail || 'Upload failed');
      }
      return res.json();
    },

    navigate(p) { this.page = p; },
  };
}
