$(document).ready(function() {
    const csrfToken = (document.querySelector('meta[name="csrf-token"]') || {}).content || '';

    const ENTITY_CONFIG = {
        site: {
            fields: [
                { key: 'code_site', type: 'text', label: 'Code Site' },
                { key: 'name', type: 'text', label: 'Site Name' },
                { key: 'supplier_id', type: 'select', label: 'Vendor', source: '/get_suppliers' },
                { key: 'commune_id', type: 'select', label: 'Commune', source: '/get_communes_all' },
                { key: 'latitude', type: 'text', label: 'Latitude' },
                { key: 'longitude', type: 'text', label: 'Longitude' },
                { key: 'address', type: 'text', label: 'Address' },
                { key: 'altitude', type: 'text', label: 'Altitude' },
                { key: 'support_nature', type: 'text', label: 'Nature Support' },
                { key: 'support_type', type: 'text', label: 'Type Support' },
                { key: 'support_height', type: 'text', label: 'Support Height (m)' },
                { key: 'status', type: 'select', label: 'Status', options: [{ id: 'Drafted', name: 'Drafted' }, { id: 'On air', name: 'On air' }] },
                { key: 'comments', type: 'text', label: 'Comments' }
            ]
        },
        sector: {
            fields: [
                { key: 'code_sector', type: 'text', label: 'Code Secteur' },
                { key: 'azimuth', type: 'text', label: 'Azimuth (deg)' },
                { key: 'hba', type: 'text', label: 'HBA' },
                { key: 'coverage_goal', type: 'text', label: 'Coverage goal' },
                { key: 'site_id', type: 'select', label: 'Site Parent', source: '/get_sites_all' }
            ]
        },
        cell: {
            fields: [
                { key: 'cellname', type: 'text', label: 'Cell Name' },
                { key: 'technology', type: 'select', label: 'Technology', options: [{ id: '2G', name: '2G' }, { id: '3G', name: '3G' }, { id: '4G', name: '4G' }, { id: '5G', name: '5G' }] },
                { key: 'frequency', type: 'text', label: 'Frequency / Band' },
                { key: 'antenna_tech', type: 'text', label: 'Antenna Tech' },
                { key: 'tilt_mechanical', type: 'text', label: 'Tilt Mechanical' },
                { key: 'tilt_electrical', type: 'text', label: 'Tilt Electrical' },
                { key: 'antenna_id', type: 'select', label: 'Antenna', source: '/get_antennas_all' },
                { key: 'sector_id', type: 'select', label: 'Parent Sector', source: '/get_sectors_all' },
                { key: 'bsc', type: 'text', label: 'BSC (2G)', tech: ['2G'] },
                { key: 'lac_2g', type: 'text', label: 'LAC (2G)', tech: ['2G'] },
                { key: 'rac_2g', type: 'text', label: 'RAC (2G)', tech: ['2G'] },
                { key: 'bcch', type: 'text', label: 'BCCH (2G)', tech: ['2G'] },
                { key: 'bsic', type: 'text', label: 'BSIC (2G)', tech: ['2G'] },
                { key: 'lac_3g', type: 'text', label: 'LAC (3G)', tech: ['3G'] },
                { key: 'rac_3g', type: 'text', label: 'RAC (3G)', tech: ['3G'] },
                { key: 'psc', type: 'text', label: 'PSC (3G)', tech: ['3G'] },
                { key: 'rnc', type: 'text', label: 'RNC (3G)', tech: ['3G'] },
                { key: 'dlarfcn', type: 'text', label: 'DLARFCN (3G)', tech: ['3G'] },
                { key: 'enodeb', type: 'text', label: 'eNodeB (4G)', tech: ['4G'] },
                { key: 'tac', type: 'text', label: 'TAC (4G)', tech: ['4G'] },
                { key: 'rsi_4g', type: 'text', label: 'RSI (4G)', tech: ['4G'] },
                { key: 'pci_4g', type: 'text', label: 'PCI (4G)', tech: ['4G'] },
                { key: 'earfcn', type: 'text', label: 'EARFCN (4G)', tech: ['4G'] },
                { key: 'gnodeb', type: 'text', label: 'GNODEB (5G)', tech: ['5G'] },
                { key: 'lac_5g', type: 'text', label: 'LAC (5G)', tech: ['5G'] },
                { key: 'rsi_5g', type: 'text', label: 'RSI (5G)', tech: ['5G'] },
                { key: 'pci_5g', type: 'text', label: 'PCI (5G)', tech: ['5G'] },
                { key: 'arfcn', type: 'text', label: 'ARFCN (5G)', tech: ['5G'] }
            ]
        },
        region: { fields: [{ key: 'name', type: 'text', label: 'Nom de la Region' }] },
        wilaya: {
            fields: [
                { key: 'id', type: 'text', label: 'Code Wilaya (ID)' },
                { key: 'name', type: 'text', label: 'Nom de la Wilaya' },
                { key: 'region_id', type: 'select', label: 'Region', source: '/get_regions' }
            ]
        },
        commune: {
            fields: [
                { key: 'name', type: 'text', label: 'Nom de la Commune' },
                { key: 'wilaya_id', type: 'select', label: 'Wilaya', source: '/get_wilayas' }
            ]
        },
        antenna: {
            fields: [
                { key: 'supplier', type: 'text', label: 'Supplier' },
                { key: 'model', type: 'text', label: 'Model Antenne' },
                { key: 'name', type: 'text', label: 'Name Antenne' },
                { key: 'frequency', type: 'text', label: 'Frequency' },
                { key: 'vbeamwidth', type: 'text', label: 'Tilt Vertical' },
                { key: 'hbeamwidth', type: 'text', label: 'Tilt Horizontal' },
                { key: 'gain', type: 'text', label: 'Gain' }
            ]
        },
        vendor: { fields: [{ key: 'name', type: 'text', label: 'Nom du Vendor' }] },
        user: {
            fields: [
                { key: 'username', type: 'text', label: 'Username' },
                { key: 'password', type: 'password', label: 'Password' },
                { key: 'is_admin', type: 'checkbox', label: 'Admin' },
                { key: 'is_active', type: 'checkbox', label: 'Active', defaultChecked: true },
                { key: 'wilaya_ids', type: 'multiselect', label: 'Wilayas', source: '/get_wilayas', bindKey: 'wilaya_id' },
                { key: 'commune_ids', type: 'multiselect', label: 'Communes', source: '/get_communes_all', dependsOn: 'wilaya_ids', bindKey: 'commune_id' },
                { key: 'site_ids', type: 'multiselect', label: 'Sites', source: '/get_sites_all', dependsOn: 'wilaya_ids', bindKey: 'site_id' }
            ]
        }
    };

    function currentEntity() {
        const rawEntity = ($('.card[data-entity]').first().data('entity') || $('#deleteBulkBtn').data('entity') || '').toLowerCase();
        return rawEntity.replace(/s$/, '');
    }

    function safeArray(value) {
        if (Array.isArray(value)) return value.map(v => String(v));
        if (value === null || value === undefined || value === '') return [];
        return [String(value)];
    }

    function updateDropdownSummary($dropdown) {
        const checked = $dropdown.find('.multi-check-item:checked');
        const total = checked.length;
        const $label = $dropdown.find('.multi-check-label');
        const $badge = $dropdown.find('.multi-count-badge');
        const base = $dropdown.data('label') || 'Select';
        $label.text(base);
        $badge.text(total);
        $badge.toggleClass('d-none', total === 0);
    }

    function applyDropdownFilter($dropdown, query) {
        const q = (query || '').trim().toLowerCase();
        $dropdown.find('.multi-option-row').each(function() {
            const txt = ($(this).data('text') || '').toLowerCase();
            const visible = !q || txt.includes(q);
            $(this).toggle(visible);
        });
    }

    function applyUserScopeLinking($scopeRoot) {
        const selectedWilayas = new Set();
        $scopeRoot.find('.multi-check-dropdown[data-key="wilaya_ids"] .multi-check-item:checked').each(function() {
            selectedWilayas.add(String($(this).val()));
        });

        function syncByWilaya(targetKey) {
            const $target = $scopeRoot.find(`.multi-check-dropdown[data-key="${targetKey}"]`);
            $target.find('.multi-option-row').each(function() {
                const itemWilaya = String($(this).data('wilaya') || '');
                const keep = selectedWilayas.size === 0 || selectedWilayas.has(itemWilaya);
                $(this).toggle(keep);
                if (selectedWilayas.size > 0 && selectedWilayas.has(itemWilaya)) {
                    $(this).find('.multi-check-item').prop('checked', true);
                }
            });
            updateDropdownSummary($target);
        }

        syncByWilaya('commune_ids');
        syncByWilaya('site_ids');
    }

    async function generateFieldHTML(field, currentValue) {
        const displayValue = (currentValue === null || currentValue === undefined) ? '' : currentValue;
        const normCurrent = String(displayValue).trim();

        if (field.type === 'checkbox') {
            const checked = (currentValue === true) || (normCurrent.toLowerCase() === 'true') || (normCurrent === '1') || (field.defaultChecked && normCurrent === '');
            return `<div class="col-md-3 mb-3 d-flex align-items-end">
                <div class="form-check form-switch">
                    <input type="checkbox" class="form-check-input" name="${field.key}" ${checked ? 'checked' : ''}>
                    <label class="form-check-label">${field.label || field.key}</label>
                </div>
            </div>`;
        }

        if (field.type === 'multiselect') {
            const selectedValues = new Set(safeArray(currentValue));
            let items = [];
            if (field.source) {
                try {
                    const res = await fetch(field.source);
                    items = await res.json();
                } catch (e) {
                    console.error('Erreur chargement multiselect:', e);
                }
            }

            let optionsHtml = '';
            items.forEach(item => {
                const value = String(item.id || item);
                const label = item.label || item.name || String(item);
                const wilayaId = item.wilaya_id || '';
                const communeId = item.commune_id || '';
                const checked = selectedValues.has(value) ? 'checked' : '';
                optionsHtml += `<div class="form-check multi-option-row" data-text="${label.replace(/"/g, '&quot;')}" data-wilaya="${wilayaId}" data-commune="${communeId}">
                    <input class="form-check-input multi-check-item" type="checkbox" name="${field.key}" value="${value}" ${checked}>
                    <label class="form-check-label">${label}</label>
                </div>`;
            });

            return `<div class="col-md-4 mb-3">
                <label class="form-label">${field.label || field.key}</label>
                <div class="dropdown multi-check-dropdown" data-key="${field.key}" data-label="${field.label || field.key}">
                    <button class="btn btn-outline-secondary w-100 text-start multi-check-toggle" type="button" data-bs-toggle="dropdown" aria-expanded="false">
                        <span class="multi-check-label">${field.label || field.key}</span>
                        <span class="badge text-bg-primary ms-2 multi-count-badge d-none">0</span>
                    </button>
                    <div class="dropdown-menu p-2 multi-check-menu w-100">
                        <input type="text" class="form-control form-control-sm mb-2 multi-filter-input" placeholder="Filter...">
                        <div class="multi-options">${optionsHtml}</div>
                    </div>
                </div>
            </div>`;
        }

        const techAttr = Array.isArray(field.tech) && field.tech.length
            ? ` data-tech-field="${field.tech.map(v => String(v).toUpperCase()).join('|')}"`
            : '';

        let html = `<div class="col-md-6 mb-3"${techAttr}>
            <label class="form-label text-capitalize">${field.label || field.key.replace(/_/g, ' ')}</label>`;

        if (field.type === 'select') {
            html += `<select name="${field.key}" class="form-select"><option value="">-- Selectionner --</option>`;
            if (Array.isArray(field.options) && field.options.length) {
                field.options.forEach(item => {
                    const itemValue = String(item.id || item.value || item);
                    const itemName = item.label || item.name || itemValue;
                    const selected = itemValue === normCurrent ? 'selected' : '';
                    html += `<option value="${itemValue}" ${selected}>${itemName}</option>`;
                });
            }
            if (field.source) {
                try {
                    const res = await fetch(field.source);
                    const items = await res.json();
                    items.forEach(item => {
                        const itemValue = String(item.id || item);
                        const itemName = item.label || item.name || item;
                        const selected = itemValue === normCurrent ? 'selected' : '';
                        html += `<option value="${itemValue}" ${selected}>${itemName}</option>`;
                    });
                } catch (e) {
                    console.error('Erreur chargement source:', e);
                }
            }
            html += '</select>';
        } else {
            const inputType = field.type === 'password' ? 'password' : 'text';
            html += `<input type="${inputType}" name="${field.key}" class="form-control" value="${field.type === 'password' ? '' : displayValue}">`;
        }

        html += '</div>';
        return html;
    }

    function initUserScopeUI($container) {
        const storagePrefix = 'user_scope_filter_';

        $container.find('.multi-check-dropdown').each(function() {
            updateDropdownSummary($(this));
        });

        $container.find('.multi-filter-input').off('input.multifilter').on('input.multifilter', function() {
            const $dropdown = $(this).closest('.multi-check-dropdown');
            const key = $dropdown.data('key');
            try {
                localStorage.setItem(storagePrefix + key, $(this).val() || '');
            } catch (e) {
                console.debug('LocalStorage unavailable', e);
            }
            applyDropdownFilter($dropdown, $(this).val());
        });

        $container.find('.multi-check-dropdown').each(function() {
            const $dropdown = $(this);
            const key = $dropdown.data('key');
            let saved = '';
            try {
                saved = localStorage.getItem(storagePrefix + key) || '';
            } catch (e) {
                saved = '';
            }
            if (saved) {
                $dropdown.find('.multi-filter-input').val(saved);
                applyDropdownFilter($dropdown, saved);
            }
        });

        $container.find('.multi-check-item').off('change.multicheck').on('change.multicheck', function() {
            const $dropdown = $(this).closest('.multi-check-dropdown');
            updateDropdownSummary($dropdown);
            applyUserScopeLinking($container);
        });

        applyUserScopeLinking($container);
    }

    function initCellTechUI($container) {
        const $tech = $container.find('[name="technology"]');
        if (!$tech.length) return;

        function refresh() {
            const tech = String($tech.val() || '').trim().toUpperCase();
            $container.find('[data-tech-field]').each(function() {
                const supported = String($(this).data('techField') || '');
                const allowed = supported.split('|').includes(tech);
                $(this).toggle(allowed);
                $(this).find('input, select').prop('disabled', !allowed);
            });
        }

        $tech.off('change.celltech').on('change.celltech', refresh);
        refresh();
    }

    function initSiteCommuneWilayaFilter($container, selectedCommuneId, preferredWilayaId) {
        // Shared Add/Edit Site helper:
        // inject a Wilaya filter and limit Commune options client-side.
        const $communeSelect = $container.find('select[name="commune_id"]');
        if (!$communeSelect.length) return;

        Promise.all([
            fetch('/get_wilayas').then(r => r.json()).catch(() => []),
            fetch('/get_communes_all').then(r => r.json()).catch(() => [])
        ]).then(function(results) {
            const wilayas = Array.isArray(results[0]) ? results[0] : [];
            const communes = Array.isArray(results[1]) ? results[1] : [];

            const $communeCol = $communeSelect.closest('.col-md-6');
            if ($communeCol.length && !$container.find('#siteWilayaFilterWrap').length) {
                const wilayaFilterHtml = `
                    <div class="col-md-6 mb-3" id="siteWilayaFilterWrap">
                        <label class="form-label">Wilaya Filter</label>
                        <select class="form-select" id="siteWilayaFilter">
                            <option value="">-- All Wilayas --</option>
                        </select>
                    </div>`;
                $communeCol.before(wilayaFilterHtml);
            }

            const $wilayaFilter = $container.find('#siteWilayaFilter');
            if (!$wilayaFilter.length) return;
            $wilayaFilter.empty().append('<option value="">-- All Wilayas --</option>');

            wilayas.forEach(function(w) {
                const wid = String(w.id || '');
                const label = w.label || w.name || wid;
                $wilayaFilter.append(`<option value="${wid}">${label}</option>`);
            });

            function renderCommuneOptions(selectedWilayaId) {
                // Preserve current selection when possible while filtering by Wilaya.
                const selectedValue = String($communeSelect.val() || selectedCommuneId || '');
                $communeSelect.empty().append('<option value="">-- Selectionner --</option>');

                communes.forEach(function(c) {
                    const cId = String(c.id || '');
                    const cName = c.name || cId;
                    const cWilaya = String(c.wilaya_id || '');
                    if (selectedWilayaId && cWilaya !== selectedWilayaId) return;
                    const selected = selectedValue && selectedValue === cId ? 'selected' : '';
                    $communeSelect.append(`<option value="${cId}" ${selected}>${cName}</option>`);
                });
            }

            let initialWilaya = String(preferredWilayaId || '');
            if (!initialWilaya && selectedCommuneId) {
                const match = communes.find(function(c) { return String(c.id) === String(selectedCommuneId); });
                if (match && match.wilaya_id !== undefined && match.wilaya_id !== null) {
                    initialWilaya = String(match.wilaya_id);
                }
            }
            if (!initialWilaya && wilayas.length === 1) {
                initialWilaya = String(wilayas[0].id || '');
            }

            $wilayaFilter.val(initialWilaya);
            renderCommuneOptions(initialWilaya);
            $wilayaFilter.off('change.siteWilaya').on('change.siteWilaya', function() {
                renderCommuneOptions(String($(this).val() || ''));
            });
        });
    }

    function collectUserPayload($form) {
        return {
            id: Number($form.find('input[name="id"]').val()),
            username: ($form.find('input[name="username"]').val() || '').trim(),
            password: $form.find('input[name="password"]').val() || '',
            is_admin: $form.find('input[name="is_admin"]').is(':checked'),
            is_active: $form.find('input[name="is_active"]').is(':checked'),
            wilaya_ids: $form.find('input[name="wilaya_ids"]:checked').map(function() { return $(this).val(); }).get(),
            commune_ids: $form.find('input[name="commune_ids"]:checked').map(function() { return $(this).val(); }).get(),
            site_ids: $form.find('input[name="site_ids"]:checked').map(function() { return $(this).val(); }).get()
        };
    }

    // Buttons visibility is handled in Jinja macro by entity type.

    $(document).on('click', '.dataTable tbody tr', function() {
        // Keep action buttons in sync with DataTable current selection count.
        setTimeout(() => {
            const table = $('.dataTable').DataTable();
            const selectedRows = table.rows({ selected: true });
            const count = selectedRows.count();
            const entity = currentEntity();

            if (count === 1) {
                const rowData = selectedRows.data()[0];
                const cleanId = $($.parseHTML(rowData[1])).text() || rowData[1];

                $('#editBtn').attr('data-id', cleanId).fadeIn();
                if (entity !== 'user') {
                    $('#deleteBulkBtn').fadeIn();
                }

                if (entity === 'site') {
                    $('#d4bBtn').attr('data-id', cleanId).fadeIn();
                    $('#siteProfileBtn').attr('data-id', cleanId).fadeIn();
                } else {
                    $('#d4bBtn, #siteProfileBtn').hide();
                }
            } else if (count > 1) {
                $('#editBtn, #d4bBtn, #siteProfileBtn').fadeOut();
                if (entity !== 'user') {
                    $('#deleteBulkBtn').fadeIn();
                }
            } else {
                $('#editBtn, #deleteBulkBtn, #d4bBtn, #siteProfileBtn').fadeOut();
            }
        }, 50);
    });

    let siteProfileMap = null;
    let siteProfileLayers = [];

    function addSiteInfoRow(label, value) {
        const safe = (value === null || value === undefined || value === '') ? '-' : value;
        return `<tr><th class="w-50">${label}</th><td>${safe}</td></tr>`;
    }

    function renderTechBadges(techList) {
        const techs = Array.isArray(techList) ? techList : [];
        if (!techs.length) {
            return '<span class="badge text-bg-secondary">N/A</span>';
        }
        const clsByTech = {
            '2G': 'text-bg-success',
            '3G': 'text-bg-info',
            '4G': 'text-bg-primary',
            '5G': 'text-bg-warning'
        };
        return techs.map(function(tech) {
            const normalized = String(tech || '').trim().toUpperCase();
            const cls = clsByTech[normalized] || 'text-bg-dark';
            return `<span class="badge ${cls}">${normalized || 'N/A'}</span>`;
        }).join('');
    }

    function renderKpiCards(site, nearestSites) {
        // Compact metric cards for quick site-level read.
        const antennaCount = Array.isArray(site.antennas) ? site.antennas.length : 0;
        const nearestCount = Array.isArray(nearestSites) ? nearestSites.length : 0;
        const cards = [
            { label: 'Sectors', value: site.sectors_count || 0, icon: 'bi-diagram-3' },
            { label: 'Cells', value: site.cells_count || 0, icon: 'bi-broadcast-pin' },
            { label: 'Antennas', value: antennaCount, icon: 'bi-reception-4' },
            { label: 'Adjacent Sites', value: nearestCount, icon: 'bi-geo-alt' }
        ];
        return cards.map(function(card) {
            return `<div class="col-6 col-lg-3">
                <div class="card border-0 shadow-sm h-100">
                    <div class="card-body py-2 px-3">
                        <div class="d-flex justify-content-between align-items-center">
                            <span class="text-muted small fw-semibold">${card.label}</span>
                            <i class="bi ${card.icon} text-primary"></i>
                        </div>
                        <div class="fs-5 fw-bold">${card.value}</div>
                    </div>
                </div>
            </div>`;
        }).join('');
    }

    function resetSiteProfileMap() {
        siteProfileLayers.forEach(function(layer) {
            if (layer && typeof layer.remove === 'function') {
                layer.remove();
            }
        });
        siteProfileLayers = [];
    }

    function destinationPoint(lat, lon, bearingDeg, distanceKm) {
        // Geodesic projection from a point + bearing + distance.
        const earthRadiusKm = 6371.0;
        const angularDistance = distanceKm / earthRadiusKm;
        const bearing = (bearingDeg * Math.PI) / 180;
        const lat1 = (lat * Math.PI) / 180;
        const lon1 = (lon * Math.PI) / 180;

        const sinLat1 = Math.sin(lat1);
        const cosLat1 = Math.cos(lat1);
        const sinAd = Math.sin(angularDistance);
        const cosAd = Math.cos(angularDistance);

        const lat2 = Math.asin(sinLat1 * cosAd + cosLat1 * sinAd * Math.cos(bearing));
        const lon2 = lon1 + Math.atan2(
            Math.sin(bearing) * sinAd * cosLat1,
            cosAd - sinLat1 * Math.sin(lat2)
        );

        return [lat2 * 180 / Math.PI, lon2 * 180 / Math.PI];
    }

    function sectorBeamRadiusKm() {
        // Fixed beam length requested by user.
        return 0.2;
    }

    function buildBeamPolygon(lat, lon, azimuth, radiusKm, beamWidthDeg) {
        // Build a wedge polygon centered on sector azimuth.
        const halfWidth = beamWidthDeg / 2;
        const start = azimuth - halfWidth;
        const end = azimuth + halfWidth;
        const points = [[lat, lon]];
        const steps = 12;
        for (let i = 0; i <= steps; i++) {
            const bearing = start + ((end - start) * i / steps);
            points.push(destinationPoint(lat, lon, bearing, radiusKm));
        }
        points.push([lat, lon]);
        return points;
    }

    function renderSiteProfileMap(site, nearestSites, sectors) {
        // Draw: main site marker, sector beams, neighboring sites and links.
        if (typeof L === 'undefined') return;

        const lat = Number(site.latitude);
        const lon = Number(site.longitude);
        if (!Number.isFinite(lat) || !Number.isFinite(lon)) return;

        if (!siteProfileMap) {
            siteProfileMap = L.map('siteProfileMap', { zoomControl: true });
            L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
                maxZoom: 19,
                attribution: '&copy; OpenStreetMap contributors'
            }).addTo(siteProfileMap);
        }

        resetSiteProfileMap();

        const bounds = [[lat, lon]];
        const mainMarker = L.circleMarker([lat, lon], {
            radius: 8,
            color: '#0d6efd',
            fillColor: '#0d6efd',
            fillOpacity: 0.95,
            weight: 2
        }).bindPopup(`<strong>${site.code_site || ''}</strong><br>${site.name || ''}`).addTo(siteProfileMap);
        siteProfileLayers.push(mainMarker);

        (sectors || []).forEach(function(sector) {
            const az = Number(sector.azimuth);
            if (!Number.isFinite(az)) return;
            const beamRadius = sectorBeamRadiusKm();
            // Fixed 40-degree beam opening requested by user.
            const beamPoints = buildBeamPolygon(lat, lon, az, beamRadius, 40);
            const beam = L.polygon(beamPoints, {
                color: '#0b5ed7',
                fillColor: '#0b5ed7',
                fillOpacity: 0.16,
                weight: 1.3
            }).bindPopup(`<strong>${sector.code_sector || '-'}</strong><br>AZ: ${sector.azimuth ?? '-'}<br>HBA: ${sector.hba ?? '-'}<br>Cells: ${sector.cells_count ?? '-'}`);
            beam.addTo(siteProfileMap);
            siteProfileLayers.push(beam);

            beamPoints.forEach(function(point) {
                bounds.push(point);
            });
        });

        (nearestSites || []).forEach(function(item) {
            const nLat = Number(item.latitude);
            const nLon = Number(item.longitude);
            if (!Number.isFinite(nLat) || !Number.isFinite(nLon)) return;

            const marker = L.circleMarker([nLat, nLon], {
                radius: 5.5,
                color: '#495057',
                fillColor: '#6c757d',
                fillOpacity: 0.9,
                weight: 1
            }).bindPopup(`<strong>${item.code_site || ''}</strong><br>${item.name || ''}<br>${item.distance_km || '-'} km`).addTo(siteProfileMap);
            siteProfileLayers.push(marker);

            const link = L.polyline([[lat, lon], [nLat, nLon]], {
                color: '#adb5bd',
                weight: 1,
                opacity: 0.8,
                dashArray: '4,4'
            }).addTo(siteProfileMap);
            siteProfileLayers.push(link);
            bounds.push([nLat, nLon]);
        });

        if (bounds.length > 1) {
            siteProfileMap.fitBounds(bounds, { padding: [28, 28] });
        } else {
            siteProfileMap.setView([lat, lon], 14);
        }
        setTimeout(function() { siteProfileMap.invalidateSize(); }, 120);
    }

    $(document).on('click', '#siteProfileBtn', function() {
        // Open modal, fetch backend payload, then hydrate UI and map.
        const siteId = ($(this).attr('data-id') || '').trim();
        if (!siteId) return;

        const modalEl = document.getElementById('siteProfileModal');
        if (!modalEl) return;
        const modal = new bootstrap.Modal(modalEl);
        modal.show();

        $('#siteProfileLoading').show();
        $('#siteProfileContent').hide();
        $('#spKpiCards').empty();
        $('#spTechBadges').empty();
        $('#spSiteInfoBody').empty();
        $('#spSectorsBody').empty();
        $('#spNearestBody').empty();
        $('#spSiteTitle').text('Site');
        $('#spOpenMapsBtn').addClass('disabled').attr('aria-disabled', 'true').attr('href', '#');

        fetch(`/site-profile/${siteId}`)
            .then(response => response.json().then(data => ({ ok: response.ok, data })))
            .then(payload => {
                if (!payload.ok || !payload.data || !payload.data.success) {
                    throw new Error((payload.data && payload.data.message) || 'Failed to load site profile');
                }

                const site = payload.data.site || {};
                const sectors = payload.data.sectors || [];
                const nearestSites = payload.data.nearest_sites || [];
                const antennas = (site.antennas || []).join(', ') || 'N/A';
                const lat = Number(site.latitude);
                const lon = Number(site.longitude);

                $('#spSiteTitle').text(`${site.code_site || ''} - ${site.name || ''}`.trim());
                $('#spKpiCards').html(renderKpiCards(site, nearestSites));
                $('#spTechBadges').html(renderTechBadges(site.techs));
                $('#spSiteInfoBody').html(
                    addSiteInfoRow('Address', site.address) +
                    addSiteInfoRow('Latitude', site.latitude) +
                    addSiteInfoRow('Longitude', site.longitude) +
                    addSiteInfoRow('Altitude', site.altitude) +
                    addSiteInfoRow('Status', site.status) +
                    addSiteInfoRow('Vendor', site.supplier_name) +
                    addSiteInfoRow('Support Nature', site.support_nature) +
                    addSiteInfoRow('Support Type', site.support_type) +
                    addSiteInfoRow('Support Height', site.support_height) +
                    addSiteInfoRow('Commune', site.commune_name) +
                    addSiteInfoRow('Wilaya', site.wilaya_name) +
                    addSiteInfoRow('Region', site.region_name) +
                    addSiteInfoRow('Antennas Deployed', antennas)
                );

                if (Number.isFinite(lat) && Number.isFinite(lon)) {
                    const mapsUrl = `https://www.google.com/maps?q=${lat},${lon}`;
                    $('#spOpenMapsBtn').removeClass('disabled').attr('aria-disabled', 'false').attr('href', mapsUrl);
                }

                if (sectors.length) {
                    let sectorsHtml = '';
                    sectors.forEach(function(s) {
                        sectorsHtml += `<tr>
                            <td>${s.code_sector || '-'}</td>
                            <td>${s.azimuth ?? '-'}</td>
                            <td>${s.hba ?? '-'}</td>
                            <td>${s.cells_count ?? '-'}</td>
                        </tr>`;
                    });
                    $('#spSectorsBody').html(sectorsHtml);
                } else {
                    $('#spSectorsBody').html('<tr><td colspan="4" class="text-muted">No sectors found.</td></tr>');
                }

                if (nearestSites.length) {
                    let nearestHtml = '';
                    nearestSites.forEach(function(n) {
                        nearestHtml += `<tr>
                            <td>${n.code_site || '-'}</td>
                            <td>${n.name || '-'}</td>
                            <td>${n.distance_km ?? '-'}</td>
                        </tr>`;
                    });
                    $('#spNearestBody').html(nearestHtml);
                } else {
                    $('#spNearestBody').html('<tr><td colspan="3" class="text-muted">No adjacent sites available.</td></tr>');
                }

                renderSiteProfileMap(site, nearestSites, sectors);
                $('#siteProfileLoading').hide();
                $('#siteProfileContent').show();
            })
            .catch(err => {
                console.error(err);
                $('#siteProfileLoading').hide();
                showToast(err.message || 'Site profile loading error', 'danger');
                modal.hide();
            });
    });

    $(document).on('click', '#addBtn', async function() {
        const entity = currentEntity() || 'site';
        const config = ENTITY_CONFIG[entity];

        if (!config) return showToast('Configuration d ajout manquante', 'danger');

        const $form = $('#addGenericForm');
        const $formContent = $('#addModalFormContent');
        const $loading = $('#addModalLoading');

        $('#addModalTitleEntity').text(entity);
        $form.attr('action', `/add_item/${entity}`);
        $formContent.empty();
        $loading.show();

        let htmlBuffer = '';
        for (const field of config.fields) {
            htmlBuffer += await generateFieldHTML(field, '');
        }

        $formContent.html(htmlBuffer);

        if (entity === 'user') {
            initUserScopeUI($formContent);
        }
        if (entity === 'cell') {
            initCellTechUI($formContent);
        }

        if (entity === 'site') {
            // Add Site: enable Wilaya->Commune filter for shorter lists.
            initSiteCommuneWilayaFilter($formContent, '', '');

            const sectorBlock = `
                <div class="col-12 mt-2" id="siteSectorBuilder" style="display:none;">
                    <div class="border rounded p-3 bg-light">
                        <h6 class="mb-3"><i class="bi bi-diagram-3 me-2"></i>Secteurs du site</h6>
                        <div class="row g-3 align-items-end">
                            <div class="col-md-4">
                                <label class="form-label">Nombre de secteurs</label>
                                <select class="form-select" id="sectorCount" name="sector_count">
                                    <option value="1">1</option><option value="2">2</option><option value="3" selected>3</option><option value="4">4</option><option value="5">5</option><option value="6">6</option>
                                </select>
                            </div>
                            <div class="col-md-8"><small class="text-muted">Les lignes de secteurs apparaissent selon le nombre choisi.</small></div>
                        </div>
                        <div id="sectorRows" class="mt-3"></div>
                    </div>
                </div>`;

            $formContent.append(sectorBlock);

            const $codeSiteInput = $formContent.find('input[name="code_site"]');
            const $sectorBuilder = $('#siteSectorBuilder');
            const $sectorCount = $('#sectorCount');
            const $sectorRows = $('#sectorRows');

            const buildSectorRows = function() {
                const codeSite = ($codeSiteInput.val() || '').trim();
                const count = parseInt($sectorCount.val() || '0', 10);

                if (!codeSite) {
                    $sectorBuilder.hide();
                    $sectorRows.empty();
                    return;
                }
                if (!Number.isFinite(count) || count < 1) {
                    $sectorRows.empty();
                    return;
                }

                $sectorBuilder.show();
                let rowsHtml = '';
                for (let i = 1; i <= count; i++) {
                    const suggestedCode = `${codeSite}_${i}`;
                    rowsHtml += `
                        <div class="row g-2 mb-2 p-2 border rounded bg-white">
                            <div class="col-md-3"><label class="form-label">Code Secteur ${i}</label><input class="form-control" name="sector_${i}_code_sector" value="${suggestedCode}" required></div>
                            <div class="col-md-2"><label class="form-label">Azimuth</label><input type="number" min="0" max="360" class="form-control" name="sector_${i}_azimuth" required></div>
                            <div class="col-md-2"><label class="form-label">HBA</label><input type="number" class="form-control" name="sector_${i}_hba" required></div>
                            <div class="col-md-5"><label class="form-label">Coverage Goal</label><input class="form-control" name="sector_${i}_coverage_goal"></div>
                        </div>`;
                }
                $sectorRows.html(rowsHtml);
            };

            $codeSiteInput.off('input.siteSector').on('input.siteSector', function() {
                if (!(($(this).val() || '').trim())) {
                    $sectorBuilder.hide();
                    $sectorRows.empty();
                    return;
                }
                buildSectorRows();
            });

            $sectorCount.off('change.siteSector').on('change.siteSector', buildSectorRows);
            buildSectorRows();
        }

        $loading.hide();
    });

    $(document).on('submit', '#addGenericForm', function(e) {
        const action = ($(this).attr('action') || '').toLowerCase();
        const entity = currentEntity();

        if (entity === 'user') {
            const username = ($(this).find('input[name="username"]').val() || '').trim();
            const password = $(this).find('input[name="password"]').val() || '';
            if (!username) {
                e.preventDefault();
                showToast('Username obligatoire.', 'warning');
                return;
            }
            if (password.length < 6) {
                e.preventDefault();
                showToast('Password minimum 6 caracteres.', 'warning');
                return;
            }
            return;
        }

        if (!action.endsWith('/add_item/site')) return;

        const $codeSite = $(this).find('input[name="code_site"]');
        const hasCodeSite = (($codeSite.val() || '').trim().length > 0);
        const hasSectorRows = $(this).find('#sectorRows .row').length > 0;

        if (!hasCodeSite && hasSectorRows) {
            e.preventDefault();
            showToast('Le code site est obligatoire avant d ajouter des secteurs.', 'warning');
            $codeSite.trigger('focus');
            return;
        }

        if (hasSectorRows) {
            const $sectorRows = $(this).find('#sectorRows .row');
            for (let idx = 0; idx < $sectorRows.length; idx++) {
                const $row = $($sectorRows[idx]);
                const sectorNumber = idx + 1;
                const $azimuth = $row.find('input[name$="_azimuth"]');
                const $hba = $row.find('input[name$="_hba"]');

                const azimuthValue = ($azimuth.val() || '').trim();
                const hbaValue = ($hba.val() || '').trim();

                if (!azimuthValue) {
                    e.preventDefault();
                    showToast(`Secteur ${sectorNumber}: azimuth est obligatoire.`, 'warning');
                    $azimuth.trigger('focus');
                    return;
                }
                if (!hbaValue) {
                    e.preventDefault();
                    showToast(`Secteur ${sectorNumber}: hba est obligatoire.`, 'warning');
                    $hba.trigger('focus');
                    return;
                }

                const azimuthNum = Number(azimuthValue);
                if (!Number.isFinite(azimuthNum) || azimuthNum < 0 || azimuthNum > 360) {
                    e.preventDefault();
                    showToast(`Secteur ${sectorNumber}: azimuth doit etre entre 0 et 360.`, 'warning');
                    $azimuth.trigger('focus');
                    return;
                }
            }
        }
    });

    $(document).on('click', '#d4bBtn', function() {
        const id = $(this).attr('data-id');
        if (id) window.location.href = `/generate_d4b/${id}`;
    });

    $(document).on('click', '.open-site-kml-modal', function() {
        const target = $(this).data('target-url') || '/export_kml/sites';
        $('#kmlSiteTarget').val(target);
        new bootstrap.Modal(document.getElementById('kmlSiteModal')).show();
    });

    $(document).on('submit', '#kmlSiteForm', function(e) {
        e.preventDefault();
        const target = ($('#kmlSiteTarget').val() || '/export_kml/sites').trim();
        const siteIcon = ($('input[name="site_icon"]:checked', this).val() || 'tower').trim();
        const siteIconScale = parseFloat($('#siteIconScale').val());
        if (!Number.isFinite(siteIconScale) || siteIconScale < 0.8 || siteIconScale > 1.8) {
            showToast('Icon scale must be between 0.8 and 1.8.', 'warning');
            return;
        }
        const query = new URLSearchParams({
            site_icon: siteIcon,
            site_icon_scale: String(siteIconScale)
        });
        bootstrap.Modal.getInstance(document.getElementById('kmlSiteModal')).hide();
        window.location.href = `${target}?${query.toString()}`;
    });

    $(document).on('click', '.open-sector-kml-modal', function() {
        const target = $(this).data('target-url') || '/export_kml/sectors';
        $('#kmlSectorTarget').val(target);
        $('#kmlBeamTitle').text('Sector Beam Export');
        new bootstrap.Modal(document.getElementById('kmlSectorModal')).show();
    });

    $(document).on('submit', '#kmlSectorForm', function(e) {
        e.preventDefault();

        const target = ($('#kmlSectorTarget').val() || '/export_kml/sectors').trim();
        const beamLength = parseFloat($('#beamLengthKm').val());
        const beamWidth = parseFloat($('#beamWidthDeg').val());
        const beamColor = ($('#beamColor').val() || '#0055ff').trim();

        if (!Number.isFinite(beamLength) || beamLength < 0.1 || beamLength > 10) {
            showToast('Beam length must be between 0.1 and 10 km.', 'warning');
            return;
        }
        if (!Number.isFinite(beamWidth) || beamWidth < 5 || beamWidth > 180) {
            showToast('Beam opening must be between 5 and 180 deg.', 'warning');
            return;
        }

        const query = new URLSearchParams({
            beam_length_km: String(beamLength),
            beam_width_deg: String(beamWidth),
            beam_color: beamColor
        });

        bootstrap.Modal.getInstance(document.getElementById('kmlSectorModal')).hide();
        window.location.href = `${target}?${query.toString()}`;
    });

    $(document).on('click', '.btn-import-direct', function() {
        const targetId = $(this).data('target-id');
        const fileInput = $('#file-input-' + targetId);
        if (fileInput.length) {
            fileInput.click();
            fileInput.off('change').on('change', function() {
                if (this.files.length > 0) $('#form-upload-' + targetId).submit();
            });
        }
    });

    $(document).on('click', '#deleteBulkBtn', function() {
        const entity = currentEntity();
        if (entity === 'user') {
            showToast('User deletion is disabled from this table.', 'info');
            return;
        }

        const table = $('.dataTable').DataTable();
        const selectedRows = table.rows({ selected: true });

        if (selectedRows.count() === 0) return;

        if (confirm('Confirmez-vous la suppression ?')) {
            const ids = [];
            selectedRows.data().each(function(rowData) {
                const cleanId = $($.parseHTML(rowData[1])).text() || rowData[1];
                ids.push(parseInt(cleanId, 10));
            });

            fetch(`/delete_items/${entity}`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-CSRF-Token': csrfToken
                },
                body: JSON.stringify({ ids })
            })
            .then(response => response.json())
            .then(data => {
                if (data.success) {
                    table.rows('.selected').remove().draw(false);
                    $('#deleteBulkBtn, #editBtn, #d4bBtn, #siteProfileBtn').fadeOut();
                    showToast(data.message, 'success');
                } else {
                    showToast(data.message || 'Delete error', 'danger');
                }
            });
        }
    });

    $(document).on('click', '#editBtn', function() {
        const targetId = $(this).attr('data-id');
        const entity = currentEntity();
        const config = ENTITY_CONFIG[entity];

        if (!config) return showToast('Configuration manquante', 'danger');

        const $formContent = $('#modalFormContent');
        const $loading = $('#modalLoading');

        $('#modalTitleEntity').text(entity);
        $formContent.hide().empty();
        $loading.show();

        const modalInstance = new bootstrap.Modal(document.getElementById('editModal'));
        modalInstance.show();

        fetch(`/get_item/${entity}/${targetId}`)
            .then(response => response.json())
            .then(async (data) => {
                let htmlBuffer = `<input type="hidden" name="id" value="${targetId}">`;

                for (const field of config.fields) {
                    htmlBuffer += await generateFieldHTML(field, data[field.key]);
                }

                $formContent.html(htmlBuffer);
                if (entity === 'site') {
                    // Edit Site: same Wilaya->Commune filtering UX as Add Site.
                    initSiteCommuneWilayaFilter($formContent, data.commune_id || '', '');
                }
                if (entity === 'user') {
                    initUserScopeUI($formContent);
                    $formContent.find('input[name="password"]').attr('placeholder', 'Leave empty to keep current password');
                }
                if (entity === 'cell') {
                    initCellTechUI($formContent);
                }
                $loading.hide();
                $formContent.fadeIn(250);
            })
            .catch(err => {
                console.error(err);
                showToast('Erreur serveur', 'danger');
                modalInstance.hide();
            });
    });

    $(document).on('submit', '#editGenericForm', function(e) {
        e.preventDefault();
        const entity = currentEntity();
        const $btn = $('#btnSaveEdit');

        $btn.html('<span class="spinner-border spinner-border-sm me-2"></span>...').prop('disabled', true);

        if (entity === 'user') {
            const payload = collectUserPayload($(this));
            if (!payload.username) {
                showToast('Username obligatoire.', 'warning');
                $btn.html('<i class="bi bi-save me-2"></i>Save').prop('disabled', false);
                return;
            }
            if (payload.password && payload.password.length < 6) {
                showToast('Password minimum 6 caracteres.', 'warning');
                $btn.html('<i class="bi bi-save me-2"></i>Save').prop('disabled', false);
                return;
            }

            fetch(`/update_item/${entity}`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-CSRF-Token': csrfToken
                },
                body: JSON.stringify(payload)
            })
            .then(response => response.json())
            .then(data => {
                if (data.success) {
                    showToast(data.message, 'success');
                    bootstrap.Modal.getInstance(document.getElementById('editModal')).hide();
                    setTimeout(() => location.reload(), 700);
                } else {
                    showToast('Erreur : ' + (data.message || 'Update error'), 'danger');
                    $btn.html('<i class="bi bi-save me-2"></i>Save').prop('disabled', false);
                }
            });
            return;
        }

        const formData = Object.fromEntries(new FormData(this));
        fetch(`/update_item/${entity}`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRF-Token': csrfToken
            },
            body: JSON.stringify(formData)
        })
        .then(response => response.json())
        .then(data => {
            if (data.success) {
                showToast(data.message, 'success');
                bootstrap.Modal.getInstance(document.getElementById('editModal')).hide();
                setTimeout(() => location.reload(), 800);
            } else {
                showToast('Erreur : ' + data.message, 'danger');
                $btn.html('<i class="bi bi-save me-2"></i>Enregistrer').prop('disabled', false);
            }
        });
    });
});
