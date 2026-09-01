from odoo.exceptions import ValidationError
from odoo import models, fields, api, _


class CpqProduct(models.Model):
    _name = 'dimension_config.product'
    _description = 'Configurable Dimension Product'
    _order = 'name'

    name = fields.Char(string='Name', required=True)
    product_tmpl_id = fields.Many2one(
        'product.template', string='Odoo Product',
        required=True, ondelete='cascade',
    )
    active = fields.Boolean(default=True)
    notes = fields.Text(string='Internal Notes')

    price_mode = fields.Selection([
        ('per_m2',     'Price per m2   (x . y . rate)'),
        ('per_m3',     'Price per m3   (x . y . z . rate)'),
        ('per_kg',     'Price per kg   (x . y . z . density . rate)'),
        ('per_linear', 'Price per meter   (x . rate)'),
        ('fixed',      'Fixed price   (surcharges only)'),
    ], string='Pricing Mode', required=True, default='per_m2')

    dimension_uom = fields.Selection([
        ('mm', 'Millimeters (mm)'),
        ('cm', 'Centimeters (cm)'),
        ('m',  'Meters (m)'),
    ], string='Dimension Unit', required=True, default='mm',
        help="Unit in which the salesperson enters the dimensions. "
             "Areas, volumes and weights are always computed in meters.")

    UOM_FACTOR = {'mm': 1000.0, 'cm': 100.0, 'm': 1.0}

    def _uom_factor(self):
        self.ensure_one()
        return self.UOM_FACTOR.get(self.dimension_uom or 'mm', 1000.0)

    # Ces quatre champs ne sont plus saisis : ils derivent du role porte par
    # chaque attribut, ce qui permet de tout definir sans sauvegarde prealable.
    length_attribute_id = fields.Many2one(
        'dimension_config.attribute', string='x  (1st dimension)',
        compute='_compute_role_attributes', store=True,
    )
    width_attribute_id = fields.Many2one(
        'dimension_config.attribute', string='y  (2nd dimension)',
        compute='_compute_role_attributes', store=True,
    )
    thickness_attribute_id = fields.Many2one(
        'dimension_config.attribute', string='z  (3rd dimension)',
        compute='_compute_role_attributes', store=True,
    )
    material_attribute_id = fields.Many2one(
        'dimension_config.attribute', string='Material',
        compute='_compute_role_attributes', store=True,
    )

    price_formula = fields.Char(compute='_compute_price_formula', store=False)

    price_per_kg     = fields.Float('Base Rate (/kg)', digits=(10, 2), default=0.0)
    price_per_m2     = fields.Float('Base Rate (/m2)', digits=(10, 2), default=0.0)
    price_per_m3     = fields.Float('Base Rate (/m3)', digits=(10, 2), default=0.0)
    price_per_linear = fields.Float('Base Rate (/m)', digits=(10, 2), default=0.0)

    attribute_ids = fields.One2many(
        'dimension_config.attribute', 'dim_product_id',
        string='Attributes', copy=True,
    )
    material_value_ids = fields.One2many(
        'dimension_config.attribute.value', 'dim_product_id',
        string='Material Grades',
        domain=[('is_material_value', '=', True)],
    )
    option_value_ids = fields.One2many(
        'dimension_config.attribute.value', 'dim_product_id',
        string='Options and Surcharges',
        domain=[('is_option_value', '=', True)],
    )
    all_value_ids = fields.One2many(
        'dimension_config.attribute.value', 'dim_product_id',
        string='All List Values',
        domain=[('attribute_id.attribute_type', '=', 'list')],
    )
    boolean_attribute_ids = fields.One2many(
        'dimension_config.attribute', 'dim_product_id',
        string='Yes/No Options',
        domain=[('attribute_type', '=', 'boolean')],
    )

    ROLES_BY_MODE = {
        'per_m2':     ['x', 'y'],
        'per_m3':     ['x', 'y', 'z'],
        'per_kg':     ['x', 'y', 'z'],
        'per_linear': ['x'],
        'fixed':      [],
    }

    @api.onchange('dimension_uom')
    def _onchange_dimension_uom(self):
        """Aligne l'unite affichee des attributs dimensionnels sur celle du produit."""
        for p in self:
            for att in p.attribute_ids:
                if att.attribute_type == 'numeric':
                    att.numeric_unit = p.dimension_uom

    def write(self, vals):
        res = super().write(vals)
        if 'dimension_uom' in vals:
            for p in self:
                atts = p.attribute_ids.filtered(lambda a: a.attribute_type == 'numeric')
                atts.filtered(lambda a: a.numeric_unit != p.dimension_uom).write(
                    {'numeric_unit': p.dimension_uom})
        return res

    @api.depends('attribute_ids.role')
    def _compute_role_attributes(self):
        for p in self:
            by_role = {}
            for att in p.attribute_ids:
                if att.role and att.role not in by_role:
                    by_role[att.role] = att
            p.length_attribute_id    = by_role.get('x', False)
            p.width_attribute_id     = by_role.get('y', False)
            p.thickness_attribute_id = by_role.get('z', False)
            p.material_attribute_id  = by_role.get('material', False)

    @api.depends('price_mode', 'length_attribute_id', 'width_attribute_id',
                 'thickness_attribute_id', 'material_attribute_id')
    def _compute_price_formula(self):
        """Formule lisible, avec les noms reellement choisis par l'utilisateur."""
        labels = {'x': 'x', 'y': 'y', 'z': 'z'}
        for p in self:
            if p.price_mode == 'fixed':
                p.price_formula = 'Price = surcharges only'
                continue
            names = {
                'x': p.length_attribute_id.name,
                'y': p.width_attribute_id.name,
                'z': p.thickness_attribute_id.name,
            }
            parts = []
            for r in p.ROLES_BY_MODE.get(p.price_mode, []):
                parts.append('%s (%s)' % (names[r], labels[r]) if names[r]
                             else '[%s to define]' % labels[r])
            if p.price_mode == 'per_kg':
                parts.append('density')
            mat = p.material_attribute_id.name
            parts.append('%s rate' % mat if mat else 'base rate')
            p.price_formula = 'Price = ' + '  x  '.join(parts) + '  + surcharges'

    @api.constrains('price_mode', 'attribute_ids')
    def _check_roles_complete(self):
        """Refuse l'enregistrement tant que la formule choisie est incomplete."""
        # Le chargement de donnees (install / demo / import) cree les
        # enregistrements de maniere incrementale : la formule est forcement
        # incomplete a mi-parcours. On ne controle donc que la saisie humaine.
        if self.env.context.get('install_mode') or self.env.context.get('import_file'):
            return
        titles = {'x': 'x (1st dimension)', 'y': 'y (2nd dimension)',
                  'z': 'z (3rd dimension)'}
        for p in self:
            missing = []
            roles = {a.role for a in p.attribute_ids if a.role}
            for r in p.ROLES_BY_MODE.get(p.price_mode, []):
                if r not in roles:
                    missing.append(titles[r])
            if p.price_mode != 'fixed' and 'material' not in roles:
                rate = {'per_m2': p.price_per_m2, 'per_m3': p.price_per_m3,
                        'per_kg': p.price_per_kg,
                        'per_linear': p.price_per_linear}.get(p.price_mode, 0.0)
                if not rate:
                    missing.append('Material (or set a Fallback Rate)')
            if missing:
                raise ValidationError(_(
                    'Please designate the attribute for: %s.\n'
                    'Open the "Attributes" tab and set the "Role in the formula" '
                    'column on the corresponding line.'
                ) % ', '.join(missing))

    pricing_warning = fields.Char(compute='_compute_pricing_warning', store=False)

    @api.depends('price_mode', 'length_attribute_id', 'width_attribute_id',
                 'thickness_attribute_id', 'material_attribute_id',
                 'price_per_kg', 'price_per_m2', 'price_per_m3', 'price_per_linear',
                 'material_value_ids.price_per_kg',
                 'material_value_ids.price_per_m2',
                 'material_value_ids.price_per_m3',
                 'material_value_ids.price_per_linear',
                 'attribute_ids.numeric_default', 'attribute_ids.role',
                 'material_value_ids.is_default')
    def _compute_pricing_warning(self):
        for p in self:
            msgs = []

            def _no_rate_anywhere(rate_field, fallback):
                """True si ni le fallback produit, ni AUCUN grade materiau
                n'a de tarif renseigne pour ce mode. Detecte le cas ou un
                materiau a ete tarife pour un AUTRE mode (ex: changement de
                price_mode sans avoir rempli le nouveau tarif)."""
                if fallback:
                    return False
                if p.material_attribute_id:
                    return not any(getattr(v, rate_field) for v in p.material_value_ids)
                return True

            if p.price_mode == 'per_kg':
                if not p.length_attribute_id: msgs.append('No attribute has the x role.')
                if not p.width_attribute_id: msgs.append('No attribute has the y role.')
                if not p.thickness_attribute_id: msgs.append('No attribute has the z role.')
                if not p.material_attribute_id and not p.price_per_kg:
                    msgs.append('No attribute has the Material role, and no Fallback Rate (/kg) is set.')
                elif _no_rate_anywhere('price_per_kg', p.price_per_kg):
                    msgs.append('No Material Grade has a Rate (/kg) set, and no Base Rate (/kg) is defined.')
            elif p.price_mode == 'per_m2':
                if not p.length_attribute_id: msgs.append('No attribute has the x role.')
                if not p.width_attribute_id: msgs.append('No attribute has the y role.')
                if not p.material_attribute_id and not p.price_per_m2:
                    msgs.append('No attribute has the Material role, and no Fallback Rate (/m2) is set.')
                elif _no_rate_anywhere('price_per_m2', p.price_per_m2):
                    msgs.append('No Material Grade has a Rate (/m2) set, and no Base Rate (/m2) is defined.')
            elif p.price_mode == 'per_m3':
                if not p.length_attribute_id: msgs.append('No attribute has the x role.')
                if not p.width_attribute_id: msgs.append('No attribute has the y role.')
                if not p.thickness_attribute_id: msgs.append('No attribute has the z role.')
                if not p.material_attribute_id and not p.price_per_m3:
                    msgs.append('No attribute has the Material role, and no Fallback Rate (/m3) is set.')
                elif _no_rate_anywhere('price_per_m3', p.price_per_m3):
                    msgs.append('No Material has a Rate (/m3) set, and no Base Rate (/m3) is defined.')
            # Un defaut a zero ou une liste sans valeur cochee font afficher
            # 0,00 a l'ouverture du configurateur : on le signale.
            if p.price_mode != 'fixed':
                zeros = p.attribute_ids.filtered(
                    lambda a: a.role in ('x', 'y', 'z')
                    and a.attribute_type == 'numeric'
                    and not a.numeric_default)
                if zeros:
                    msgs.append('Set a realistic default value for: %s. '
                                'Without it the configurator opens at 0.00 and your '
                                'salesperson may send a quotation at zero.'
                                % ', '.join(zeros.mapped('name')))
                if p.material_attribute_id and p.material_attribute_id.value_ids \
                        and not p.material_attribute_id.value_ids.filtered('is_default'):
                    msgs.append('No default material is ticked, so the configurator '
                                'will open at 0.00.')
            if p.price_mode == 'per_linear':
                if not p.length_attribute_id: msgs.append('No attribute has the x role.')
                if not p.material_attribute_id and not p.price_per_linear:
                    msgs.append('No attribute has the Material role, and no Fallback Rate (/m) is set.')
                elif _no_rate_anywhere('price_per_linear', p.price_per_linear):
                    msgs.append('No Material Grade has a Rate (/m) set, and no Base Rate (/m) is defined.')
            p.pricing_warning = '  \u26a0  ' + '  \u00b7  '.join(msgs) if msgs else False


class CpqAttribute(models.Model):
    _name = 'dimension_config.attribute'
    _description = 'Dimension Product Configurator Attribute'
    _order = 'dim_product_id, sequence, id'

    dim_product_id  = fields.Many2one('dimension_config.product', required=True, ondelete='cascade')
    name            = fields.Char(string='Name', required=True)
    sequence        = fields.Integer(default=10)
    attribute_type  = fields.Selection([
        ('list',    'Selection list'),
        ('numeric', 'Numeric'),
        ('boolean', 'Yes / No'),
    ], string='Type', required=True)
    role            = fields.Selection([
        ('x',        'x  (1st dimension)'),
        ('y',        'y  (2nd dimension)'),
        ('z',        'z  (3rd dimension)'),
        ('material', 'Material'),
    ], string='Role in the formula',
        help="Designates the part this attribute plays in the price formula. "
             "Leave empty for options that only add a surcharge.")
    is_required     = fields.Boolean(string='Required', default=True)
    numeric_min     = fields.Float('Min', default=1.0)
    numeric_max     = fields.Float('Max', default=9999.0)
    numeric_unit    = fields.Char('Unit', default='mm')
    numeric_default = fields.Float('Default', default=0.0)
    value_ids       = fields.One2many('dimension_config.attribute.value', 'attribute_id',
                                       string='Values', copy=True)
    bool_surcharge  = fields.Float('Surcharge if Yes', default=0.0)
    bool_default    = fields.Boolean('Default', default=False)

    @api.onchange('numeric_min', 'numeric_max', 'numeric_default')
    def _onchange_numeric_bounds(self):
        """Un defaut a zero fait afficher un prix nul a l'ouverture du
        configurateur : on le ramene toujours dans les bornes."""
        for att in self:
            if att.attribute_type != 'numeric' or not att.numeric_default:
                continue
            if att.numeric_default < att.numeric_min:
                att.numeric_default = att.numeric_min
            elif att.numeric_max and att.numeric_default > att.numeric_max:
                att.numeric_default = att.numeric_max

    @api.onchange('attribute_type', 'role')
    def _onchange_type_role(self):
        """Un role dimensionnel implique un attribut numerique, et l'unite
        de saisie doit suivre celle definie sur le produit."""
        for att in self:
            if att.role in ('x', 'y', 'z'):
                att.attribute_type = 'numeric'
            elif att.role == 'material':
                att.attribute_type = 'list'
            if att.attribute_type == 'numeric':
                uom = att.dim_product_id.dimension_uom
                if uom:
                    att.numeric_unit = uom

    @api.model_create_multi
    def create(self, vals_list):
        # Le JS envoie toujours attribute_type='list' (1ere option Selection).
        # On force depuis le contexte quand il est defini (ex: boolean_attribute_ids).
        ctx_type = self.env.context.get('default_attribute_type')
        for vals in vals_list:
            if ctx_type:
                vals['attribute_type'] = ctx_type
            elif not vals.get('attribute_type'):
                vals['attribute_type'] = 'list'
            # Un role dimensionnel implique un attribut numerique.
            if vals.get('role') in ('x', 'y', 'z'):
                vals['attribute_type'] = 'numeric'
            elif vals.get('role') == 'material':
                vals['attribute_type'] = 'list'
        records = super().create(vals_list)
        # L'unite de saisie suit celle du produit : les onchange ne se
        # declenchent qu'en interface, on securise donc aussi cote serveur.
        for rec in records:
            uom = rec.dim_product_id.dimension_uom
            if rec.attribute_type == 'numeric' and uom and rec.numeric_unit != uom:
                rec.numeric_unit = uom
        records._enforce_numeric_default()
        return records

    def write(self, vals):
        res = super().write(vals)
        if {'numeric_min', 'numeric_max', 'numeric_default', 'attribute_type'} & set(vals):
            self._enforce_numeric_default()
        return res

    def _ensure_default_value(self):
        """Un attribut liste sans valeur par defaut ouvre le configurateur
        sur un choix vide, donc sur un prix nul. On coche la premiere."""
        for att in self:
            if att.attribute_type != 'list' or not att.value_ids:
                continue
            defaults = att.value_ids.filtered('is_default')
            if not defaults:
                att.value_ids[0].is_default = True
            elif len(defaults) > 1:
                (defaults - defaults[0]).is_default = False

    def _enforce_numeric_default(self):
        """Le defaut d'un attribut numerique doit rester dans ses bornes,
        sans quoi le configurateur s'ouvre sur un prix nul."""
        for att in self:
            if att.attribute_type != 'numeric':
                continue
            # Un defaut a zero signifie "non renseigne" : on ne devine pas une
            # dimension a la place de l'utilisateur, le garde-fou l'alerte.
            # On se contente de ramener dans les bornes un defaut deja saisi.
            if not att.numeric_default:
                continue
            new = att.numeric_default
            if new < att.numeric_min:
                new = att.numeric_min
            elif att.numeric_max and new > att.numeric_max:
                new = att.numeric_max
            if new != att.numeric_default:
                att.numeric_default = new


class CpqAttributeValue(models.Model):
    _name = 'dimension_config.attribute.value'
    _description = 'Dimension Product Configurator Attribute Value'
    _order = 'attribute_id, sequence, id'

    attribute_id   = fields.Many2one('dimension_config.attribute', required=True, ondelete='cascade')
    dim_product_id = fields.Many2one('dimension_config.product', store=True, index=True)

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if not vals.get('dim_product_id') and vals.get('attribute_id'):
                attr = self.env['dimension_config.attribute'].browse(vals['attribute_id'])
                vals['dim_product_id'] = attr.dim_product_id.id
        records = super().create(vals_list)
        records.attribute_id._ensure_default_value()
        return records

    def write(self, vals):
        res = super().write(vals)
        if 'is_default' in vals:
            self.attribute_id._ensure_default_value()
        return res

    def unlink(self):
        attrs = self.attribute_id
        res = super().unlink()
        attrs.exists()._ensure_default_value()
        return res

    name              = fields.Char(string='Value', required=True)
    attribute_name    = fields.Char(related='attribute_id.name', string='Attribute',
                                    store=True, readonly=True)
    sequence          = fields.Integer(default=10)
    surcharge         = fields.Float('Surcharge', default=0.0)
    is_default        = fields.Boolean('Default', default=False)
    density           = fields.Float('Density (kg/m3)', default=0.0)
    price_per_kg      = fields.Float('Rate per kg', default=0.0)
    price_per_m2      = fields.Float('Rate per m2', default=0.0)
    price_per_m3      = fields.Float('Rate per m3', default=0.0)
    price_per_linear  = fields.Float('Rate per linear meter', default=0.0)

    is_material_value = fields.Boolean(
        'Is Material Grade', compute='_compute_material_flags', store=True, index=True,
    )
    is_option_value = fields.Boolean(
        'Is Option/Surcharge', compute='_compute_material_flags', store=True, index=True,
    )

    @api.depends('attribute_id', 'attribute_id.attribute_type',
                 'attribute_id.dim_product_id.material_attribute_id')
    def _compute_material_flags(self):
        for v in self:
            attr = v.attribute_id
            prod = attr.dim_product_id
            is_mat = bool(prod.material_attribute_id and prod.material_attribute_id == attr)
            v.is_material_value = is_mat
            v.is_option_value = (attr.attribute_type == 'list' and not is_mat)

    price_unit    = fields.Char(compute='_compute_price_unit')
    display_price = fields.Float(compute='_compute_display_price',
                                  inverse='_set_display_price', digits=(10, 2))

    @api.depends('attribute_id.dim_product_id.material_attribute_id',
                 'attribute_id.dim_product_id.price_mode')
    def _compute_price_unit(self):
        currency = self.env.company.currency_id.name or 'EUR'
        for v in self:
            if v.is_material_value:
                mode = v.attribute_id.dim_product_id.price_mode
                if mode == 'per_m2':
                    v.price_unit = f'{currency}/m2'
                elif mode == 'per_m3':
                    v.price_unit = f'{currency}/m3'
                elif mode == 'per_linear':
                    v.price_unit = f'{currency}/m'
                else:
                    v.price_unit = f'{currency}/kg'
            else:
                v.price_unit = currency

    @api.depends('price_per_kg', 'price_per_m2', 'price_per_m3', 'price_per_linear',
                 'surcharge', 'is_material_value',
                 'attribute_id.dim_product_id.price_mode')
    def _compute_display_price(self):
        for v in self:
            if v.is_material_value:
                mode = v.attribute_id.dim_product_id.price_mode
                if mode == 'per_m2':
                    v.display_price = v.price_per_m2
                elif mode == 'per_m3':
                    v.display_price = v.price_per_m3
                elif mode == 'per_linear':
                    v.display_price = v.price_per_linear
                else:
                    v.display_price = v.price_per_kg
            else:
                v.display_price = v.surcharge

    def _set_display_price(self):
        for v in self:
            if v.is_material_value:
                mode = v.attribute_id.dim_product_id.price_mode
                if mode == 'per_m2':
                    v.price_per_m2 = v.display_price
                elif mode == 'per_m3':
                    v.price_per_m3 = v.display_price
                elif mode == 'per_linear':
                    v.price_per_linear = v.display_price
                else:
                    v.price_per_kg = v.display_price
            else:
                v.surcharge = v.display_price



