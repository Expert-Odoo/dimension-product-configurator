from odoo import models, fields, api


class CpqConfiguration(models.Model):
    _name = 'dimension_config.configuration'
    _description = 'Saved Dimension Product Configurator Configuration'

    sale_line_id = fields.Many2one(
        'sale.order.line', string='Quotation Line',
        required=True, ondelete='cascade',
    )
    dim_product_id = fields.Many2one(
        'dimension_config.product', string='Configurable Product', required=True,
    )
    value_ids = fields.One2many(
        'dimension_config.configuration.value', 'configuration_id',
        string='Values', copy=True,
    )
    price_unit = fields.Float('Unit Price (excl. tax)', digits=(16, 2))
    weight_kg  = fields.Float('Weight (kg)', digits=(16, 4))
    surface_m2 = fields.Float('Area (m2)', digits=(16, 4))
    volume_m3  = fields.Float('Volume (m3)', digits=(16, 4))
    summary    = fields.Text('Summary', compute='_compute_summary', store=True)

    @api.depends('value_ids', 'value_ids.value_list_id',
                 'value_ids.value_numeric', 'value_ids.value_boolean',
                 'dim_product_id.length_attribute_id',
                 'dim_product_id.width_attribute_id',
                 'dim_product_id.thickness_attribute_id',
                 'dim_product_id.material_attribute_id')
    def _compute_summary(self):
        for config in self:
            uom = config.dim_product_id.dimension_uom or 'mm'
            product = config.dim_product_id
            L_attr = product.length_attribute_id
            l_attr = product.width_attribute_id
            e_attr = product.thickness_attribute_id
            m_attr = product.material_attribute_id
            parts = []

            for val in config.value_ids.sorted(lambda v: v.attribute_id.sequence):
                attr = val.attribute_id
                if L_attr and attr == L_attr:
                    parts.append('%s %g %s' % (attr.name, val.value_numeric, uom))
                elif l_attr and attr == l_attr:
                    parts.append('%s %g %s' % (attr.name, val.value_numeric, uom))
                elif e_attr and attr == e_attr:
                    parts.append('%s %g %s' % (attr.name, val.value_numeric, uom))
                elif m_attr and attr == m_attr:
                    if val.value_list_id:
                        parts.append(val.value_list_id.name)
                elif attr.attribute_type == 'list' and val.value_list_id:
                    parts.append(val.value_list_id.name)
                elif attr.attribute_type == 'boolean' and val.value_boolean:
                    parts.append(attr.name)
                elif attr.attribute_type == 'numeric':
                    unit = attr.numeric_unit or ''
                    parts.append('%s: %g %s' % (attr.name, val.value_numeric, unit))

            mode = config.dim_product_id.price_mode
            if mode == 'per_kg' and config.weight_kg:
                parts.append('%.3f kg' % config.weight_kg)
            elif mode == 'per_m3' and config.volume_m3:
                parts.append('%.4f m3' % config.volume_m3)
            elif mode == 'per_m2' and config.surface_m2:
                parts.append('%.4f m2' % config.surface_m2)
            config.summary = ' - '.join(parts)

    def get_pdf_breakdown(self):
        self.ensure_one()
        currency = self.env.company.currency_id.name or 'EUR'
        product = self.dim_product_id
        L_attr = product.length_attribute_id
        l_attr = product.width_attribute_id
        e_attr = product.thickness_attribute_id
        m_attr = product.material_attribute_id
        price_mode = product.price_mode

        L_mm = l_mm = e_mm = 0.0
        density = price_kg = price_m2 = price_linear = 0.0
        material_name = ''
        surcharges = []

        vals_by_attr = {v.attribute_id.id: v for v in self.value_ids}

        if L_attr:
            wl = vals_by_attr.get(L_attr.id)
            if wl: L_mm = wl.value_numeric
        if l_attr:
            wl = vals_by_attr.get(l_attr.id)
            if wl: l_mm = wl.value_numeric
        if e_attr:
            wl = vals_by_attr.get(e_attr.id)
            if wl: e_mm = wl.value_numeric

        if m_attr:
            mv = vals_by_attr.get(m_attr.id)
            if mv and mv.value_list_id:
                density = mv.value_list_id.density
                price_kg = mv.value_list_id.price_per_kg
                price_m2 = mv.value_list_id.price_per_m2
                price_linear = mv.value_list_id.price_per_linear
                material_name = mv.value_list_id.name

        if not density:
            density = 7850.0
        if not price_kg:
            price_kg = product.price_per_kg
        if not price_m2:
            price_m2 = product.price_per_m2
        if not price_linear:
            price_linear = product.price_per_linear
        if not material_name:
            material_name = product.name

        skip_ids = {a.id for a in [L_attr, l_attr, e_attr, m_attr] if a}

        for val in self.value_ids.sorted(lambda v: v.attribute_id.sequence):
            if val.attribute_id.id in skip_ids:
                continue
            attr = val.attribute_id
            if attr.attribute_type == 'list' and val.value_list_id and val.value_list_id.surcharge:
                surcharges.append({
                    'label': '%s %s' % (attr.name, val.value_list_id.name),
                    'amount': val.value_list_id.surcharge,
                })
            elif attr.attribute_type == 'boolean' and val.value_boolean and attr.bool_surcharge:
                surcharges.append({'label': attr.name, 'amount': attr.bool_surcharge})

        lines = []
        uom = product.dimension_uom or 'mm'
        factor = product._uom_factor()
        if price_mode == 'per_kg':
            L_m = L_mm / factor
            l_m = l_mm / factor
            e_m = e_mm / factor
            weight = L_m * l_m * e_m * density
            base = weight * price_kg
            lines.append({'label': 'Dimensions: %g x %g x %g %s' % (L_mm, l_mm, e_mm, uom), 'amount': False})
            lines.append({'label': '%s  %.4f m3 x %.0f kg/m3 = %.3f kg' % (material_name, L_m*l_m*e_m, density, weight), 'amount': False})
            lines.append({'label': '%.3f kg x %.2f %s/kg' % (weight, price_kg, currency), 'amount': base})
        elif price_mode == 'per_m2':
            L_m = L_mm / factor
            l_m = l_mm / factor
            surface = L_m * l_m
            base = surface * price_m2
            lines.append({'label': '%g x %g %s  ->  %.4f m2' % (L_mm, l_mm, uom, surface), 'amount': False})
            lines.append({'label': '%s: %.4f m2 x %.2f %s/m2' % (material_name, surface, price_m2, currency), 'amount': base})
        elif price_mode == 'per_m3':
            L_m = L_mm / factor
            l_m = l_mm / factor
            e_m = e_mm / factor
            volume = L_m * l_m * e_m
            base = volume * (product.price_per_m3 or 0.0)
            if m_attr:
                mv = vals_by_attr.get(m_attr.id)
                if mv and mv.value_list_id and mv.value_list_id.price_per_m3:
                    base = volume * mv.value_list_id.price_per_m3
            lines.append({'label': '%g x %g x %g %s  ->  %.4f m3' % (L_mm, l_mm, e_mm, uom, volume), 'amount': False})
            lines.append({'label': '%s: %.4f m3' % (material_name, volume), 'amount': base})
        elif price_mode == 'per_linear':
            L_m = L_mm / factor
            base = L_m * price_linear
            lines.append({'label': '%g %s  ->  %.3f m' % (L_mm, uom, L_m), 'amount': False})
            lines.append({'label': '%s: %.3f m x %.2f %s/m' % (material_name, L_m, price_linear, currency), 'amount': base})
        else:
            base = 0.0

        for s in surcharges:
            lines.append(s)

        total = (base or 0.0) + sum(s['amount'] for s in surcharges)
        return {'lines': lines, 'total': total}


class CpqConfigurationValue(models.Model):
    _name = 'dimension_config.configuration.value'
    _description = 'Dimension Product Configurator Configuration Value'

    configuration_id = fields.Many2one(
        'dimension_config.configuration', required=True, ondelete='cascade',
    )
    attribute_id  = fields.Many2one('dimension_config.attribute', ondelete='cascade')
    value_list_id = fields.Many2one('dimension_config.attribute.value')
    value_numeric = fields.Float(digits=(10, 4))
    value_boolean = fields.Boolean()

