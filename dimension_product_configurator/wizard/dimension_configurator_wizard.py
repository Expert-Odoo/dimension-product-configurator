# Dimension Product Configurator - configurator wizard
from odoo import models, fields, api
from odoo.exceptions import UserError


class CpqConfiguratorWizard(models.TransientModel):
    _name = 'dimension_config.configurator.wizard'
    _description = 'Dimension Product Configurator Configurator'

    sale_line_id    = fields.Many2one('sale.order.line', required=True, ondelete='cascade')
    dim_product_id  = fields.Many2one('dimension_config.product', required=True)
    line_ids        = fields.One2many('dimension_config.configurator.wizard.line', 'wizard_id')
    price_total     = fields.Float('Total Price (excl. tax)', digits=(16, 2), readonly=True)
    price_mode      = fields.Selection(related='dim_product_id.price_mode', readonly=True)
    weight_kg       = fields.Float('Weight (kg)', digits=(16, 3), readonly=True)
    surface_m2      = fields.Float('Area (m2)', digits=(16, 4), readonly=True)
    volume_m3       = fields.Float('Volume (m3)', digits=(16, 4), readonly=True)
    price_breakdown = fields.Text('Price breakdown', readonly=True)

    def _init_lines(self):
        self.ensure_one()
        if self.line_ids:
            self.line_ids.unlink()
        existing = self.sale_line_id.dim_configuration_id
        lines = []
        if existing:
            for cval in existing.value_ids.sorted(lambda v: v.attribute_id.sequence):
                lines.append((0, 0, {
                    'attribute_id':  cval.attribute_id.id,
                    'value_list_id': cval.value_list_id.id if cval.value_list_id else False,
                    'value_numeric': cval.value_numeric,
                    'value_boolean': cval.value_boolean,
                }))
        else:
            for attr in self.dim_product_id.attribute_ids.sorted('sequence'):
                default_list = attr.value_ids.filtered('is_default')[:1]
                lines.append((0, 0, {
                    'attribute_id':  attr.id,
                    'value_list_id': default_list.id if attr.attribute_type == 'list' and default_list else False,
                    'value_numeric': attr.numeric_default if attr.attribute_type == 'numeric' else 0.0,
                    'value_boolean': attr.bool_default    if attr.attribute_type == 'boolean' else False,
                }))
        if lines:
            self.write({'line_ids': lines})
        self._recompute_price()

    @api.onchange('line_ids')
    def _onchange_lines(self):
        self._recompute_price()

    def _recompute_price(self):
        self.ensure_one()
        currency   = self.env.company.currency_id.name or 'EUR'
        product    = self.dim_product_id
        price_mode = product.price_mode
        vals_by_attr = {wl.attribute_id.id: wl for wl in self.line_ids}
        L_raw = l_raw = e_raw = 0.0
        uom = product.dimension_uom or 'mm'
        factor = product._uom_factor()
        density = price_kg = price_m2 = price_m3 = price_linear = 0.0
        material_name = ''
        surcharges = []
        if product.length_attribute_id:
            wl = vals_by_attr.get(product.length_attribute_id.id)
            if wl: L_raw = wl.value_numeric
        if product.width_attribute_id and price_mode in ('per_kg', 'per_m2', 'per_m3'):
            wl = vals_by_attr.get(product.width_attribute_id.id)
            if wl: l_raw = wl.value_numeric
        if price_mode in ('per_kg', 'per_m3') and product.thickness_attribute_id:
            wl = vals_by_attr.get(product.thickness_attribute_id.id)
            if wl: e_raw = wl.value_numeric
        if product.material_attribute_id:
            wl = vals_by_attr.get(product.material_attribute_id.id)
            if wl and wl.value_list_id:
                density = wl.value_list_id.density
                price_kg = wl.value_list_id.price_per_kg
                price_m2 = wl.value_list_id.price_per_m2
                price_m3 = wl.value_list_id.price_per_m3
                price_linear = wl.value_list_id.price_per_linear
                material_name = wl.value_list_id.name
        skip_ids = {
            product.length_attribute_id.id    if product.length_attribute_id    else None,
            product.width_attribute_id.id     if product.width_attribute_id     else None,
            product.thickness_attribute_id.id if product.thickness_attribute_id else None,
            product.material_attribute_id.id  if product.material_attribute_id  else None,
        }
        skip_ids.discard(None)
        for wl in self.line_ids.sorted(lambda l: l.attribute_id.sequence):
            if wl.attribute_id.id in skip_ids:
                continue
            attr = wl.attribute_id
            if attr.attribute_type == 'list' and wl.value_list_id and wl.value_list_id.surcharge:
                surcharges.append((attr.name, wl.value_list_id.name, wl.value_list_id.surcharge))
            elif attr.attribute_type == 'boolean' and wl.value_boolean and attr.bool_surcharge:
                surcharges.append((attr.name, '', attr.bool_surcharge))
        weight = surface = volume = 0.0
        base = 0.0
        breakdown_lines = []
        L_m = L_raw / factor
        l_m = l_raw / factor
        e_m = e_raw / factor
        if price_mode == 'per_kg':
            if not density: density = 7850.0
            if not price_kg: price_kg = product.price_per_kg
            if not material_name: material_name = product.name
            volume = L_m * l_m * e_m
            weight = volume * density
            base = weight * price_kg
            breakdown_lines.append(
                '%g x %g x %g %s  ->  %.3f kg  x  %.2f %s/kg  =  %.2f %s' % (
                    L_raw, l_raw, e_raw, uom, weight, price_kg, currency, base, currency)
            )
        elif price_mode == 'per_m2':
            if not price_m2: price_m2 = product.price_per_m2
            if not material_name: material_name = product.name
            surface = L_m * l_m
            base = surface * price_m2
            breakdown_lines.append(
                '%g x %g %s  ->  %.4f m2  x  %.2f %s/m2  =  %.2f %s' % (
                    L_raw, l_raw, uom, surface, price_m2, currency, base, currency)
            )
        elif price_mode == 'per_m3':
            if not price_m3: price_m3 = product.price_per_m3
            if not material_name: material_name = product.name
            surface = L_m * l_m
            volume = surface * e_m
            base = volume * price_m3
            breakdown_lines.append(
                '%g x %g x %g %s  ->  %.4f m3  x  %.2f %s/m3  =  %.2f %s' % (
                    L_raw, l_raw, e_raw, uom, volume, price_m3, currency, base, currency)
            )
        elif price_mode == 'per_linear':
            if not price_linear: price_linear = product.price_per_linear
            if not material_name: material_name = product.name
            base = L_m * price_linear
            breakdown_lines.append(
                '%g %s  ->  %.3f m  x  %.2f %s/m  =  %.2f %s' % (
                    L_raw, uom, L_m, price_linear, currency, base, currency)
            )
        for sname, soption, samount in surcharges:
            label = '%s %s' % (sname, soption) if soption else sname
            breakdown_lines.append('%s: +%.2f %s' % (label, samount, currency))
        total = base + sum(s[2] for s in surcharges)
        self.weight_kg      = weight
        self.surface_m2     = surface
        self.volume_m3      = volume
        self.price_total    = total
        self.price_breakdown = '\n'.join(breakdown_lines) if breakdown_lines else ''

    def _get_lines_to_validate(self):
        return self.line_ids

    def _validate_configuration(self):
        """Valide CHAQUE attribut configure dans le devis :
        - numerique : doit etre dans [numeric_min, numeric_max] si renseigne ;
          si is_required, doit etre renseigne (non nul/non vide).
        - liste : si is_required, une valeur doit etre selectionnee.
        - booleen : toujours valide (case a cocher, valeur par defaut existe).
        Remplace l\'ancienne validation qui ne verifiait que L/W/T > 0 et
        ignorait totalement les bornes min/max et les champs liste requis.
        """
        self.ensure_one()
        errors = []
        for wl in self._get_lines_to_validate():
            attr = wl.attribute_id
            if attr.attribute_type == 'numeric':
                value = wl.value_numeric
                if not value:
                    if attr.is_required:
                        errors.append('%s is required.' % attr.name)
                    continue
                if value < attr.numeric_min or value > attr.numeric_max:
                    unit = (' %s' % attr.numeric_unit) if attr.numeric_unit else ''
                    errors.append(
                        '%s must be between %g and %g%s (got %g%s).' % (
                            attr.name, attr.numeric_min, attr.numeric_max,
                            unit, value, unit)
                    )
            elif attr.attribute_type == 'list':
                if attr.is_required and not wl.value_list_id:
                    errors.append('%s is required.' % attr.name)
        if errors:
            raise UserError('\n'.join(errors))

    def action_confirm(self):
        self.ensure_one()
        self._validate_configuration()
        self._recompute_price()
        sale_line = self.sale_line_id
        product = self.dim_product_id
        config_vals = {
            'sale_line_id': sale_line.id,
            'dim_product_id': product.id,
            'price_unit': self.price_total,
            'weight_kg': self.weight_kg,
            'surface_m2': self.surface_m2,
            'volume_m3': self.volume_m3,
        }
        existing = sale_line.dim_configuration_id
        if existing:
            existing.value_ids.unlink()
            existing.write(config_vals)
            config = existing
        else:
            config = self.env['dimension_config.configuration'].create(config_vals)
        value_vals = []
        for wl in self.line_ids:
            value_vals.append({
                'configuration_id': config.id,
                'attribute_id': wl.attribute_id.id,
                'value_list_id': wl.value_list_id.id if wl.value_list_id else False,
                'value_numeric': wl.value_numeric,
                'value_boolean': wl.value_boolean,
            })
        self.env['dimension_config.configuration.value'].create(value_vals)
        sale_line.write({
            'dim_configuration_id': config.id,
            'price_unit': self.price_total,
            'name': config.summary or sale_line.name,
        })
        return {'type': 'ir.actions.act_window_close'}


class CpqConfiguratorWizardLine(models.TransientModel):
    _name = 'dimension_config.configurator.wizard.line'
    _description = 'Dimension Product Configurator Configurator Line'
    _order = 'sequence, attribute_id'

    wizard_id     = fields.Many2one('dimension_config.configurator.wizard', ondelete='cascade')
    sequence      = fields.Integer(default=10)
    attribute_id  = fields.Many2one('dimension_config.attribute', required=True)
    value_list_id = fields.Many2one(
        'dimension_config.attribute.value',
        domain="[('attribute_id', '=', attribute_id)]",
    )
    value_numeric = fields.Float(digits=(10, 2))
    value_boolean = fields.Boolean()

    attribute_type  = fields.Selection(related='attribute_id.attribute_type', readonly=True)
    numeric_unit    = fields.Char(related='attribute_id.numeric_unit', readonly=True)
    numeric_min     = fields.Float(related='attribute_id.numeric_min', readonly=True)
    numeric_max     = fields.Float(related='attribute_id.numeric_max', readonly=True)
    attribute_label = fields.Char(compute='_compute_attribute_label')
    all_value_ids   = fields.Many2many(
        'dimension_config.attribute.value',
        compute='_compute_all_value_ids',
    )

    @api.depends('attribute_id', 'attribute_id.name', 'attribute_id.numeric_unit')
    def _compute_attribute_label(self):
        for line in self:
            attr = line.attribute_id
            if attr.attribute_type == 'numeric' and attr.numeric_unit:
                line.attribute_label = '%s (%s)' % (attr.name, attr.numeric_unit)
            else:
                line.attribute_label = attr.name or ''

    @api.depends('attribute_id')
    def _compute_all_value_ids(self):
        for line in self:
            line.all_value_ids = line.attribute_id.value_ids


