<template>
  <v-container fluid inventory>
    <v-combobox
      v-model="model"
      :filter="filter"
      :hide-no-data="!search"
      :items="items"
      :search-input.sync="search"
      hide-selected
      :label="label"
      multiple
      small-chips
      @change="change"
    >
      <template v-slot:no-data>
        <v-list-item>
          <span class="subheading">Create</span>
          <v-chip label small>{{ search }}</v-chip>
        </v-list-item>
      </template>
      <template v-slot:selection="{ attrs, item, parent, selected }">
        <v-chip v-if="item === Object(item)" v-bind="attrs" :input-value="selected" label small>
          <span class="pr-2">{{ item.text }}</span>
          <v-icon small @click="parent.selectItem(item)">$delete</v-icon>
        </v-chip>
      </template>
      <template v-slot:item="{ index, item }">
        <v-text-field
          v-if="editing === item"
          v-model="editing.text"
          autofocus
          flat
          background-color="transparent"
          hide-details
          solo
          @keyup.enter="edit(index, item)"
        ></v-text-field>
        <v-chip v-else dark label small>{{ item.text }}</v-chip>

        <v-spacer></v-spacer>
        <v-list-item-action @click.stop>
          <v-text-field
            v-model="item.input_value"
            type="number"
            :label="`all curr_qty ${item.all}`"
            hint
            :min="0"
            :max="item.all"
            oninput="if(Number(this.value) > Number(this.max)) this.value = this.max;"
            clearable
            width="140px"
          ></v-text-field>
          <!-- <v-btn icon @click.stop.prevent="edit(index, item)">
            <v-icon>{{ editing !== item ? 'mdi-pencil' : 'mdi-check' }}</v-icon>
          </v-btn>-->
        </v-list-item-action>
      </template>
    </v-combobox>
  </v-container>
</template>

<script>
import { cloneDeep } from "lodash";

export default {
  name: "InventoryConbobox",
  props: {
    value: {
      type: Array,
      default: function () {
        return [];
      },
    },
    items: {
      type: Array,
      default: function () {
        return [];
      },
    },
    label: {
      type: String,
      default: function () {
        return "Inventory Select";
      },
    },
  },
  data: () => ({
    value_num: 10,
    activator: null,
    attach: null,
    colors: ["green", "purple", "indigo", "cyan", "teal", "orange"],
    editing: null,
    editingIndex: -1,
    // items: [
    //   { header: "Select an option" },
    //   {
    //     text: "book/school",
    //     all: 100,
    //     input_value: 10,
    //   },
    //   {
    //     text: "desk/school",
    //     all: 100,
    //     input_value: 10,
    //   },
    // ],
    // model: [],
    nonce: 1,
    menu: false,
    x: 0,
    search: null,
    y: 0,
  }),

  computed: {
    model: {
      get() {
        return cloneDeep(this.value);
      },
      set(value) {
        this.$emit("input", value);
      },
    },
  },
  watch: {
    model(val, prev) {
      if (val == null) {
        return [];
      }
      if (prev != null && val != null && val.length === prev.length) return;
      this.model = val.map((v) => {
        if (typeof v === "string") {
          v = {
            text: v,
            color: this.colors[this.nonce - 1],
          };

          this.items.push(v);

          this.nonce++;
        }

        return v;
      });
    },
  },

  methods: {
    change(value_list) {
      // debugger;
      let model_list = [];
      if (value_list) {
        this.model = value_list.reduce((pre, cur, index) => {
          if (cur.input_value == undefined) {
            if (model_list.indexOf(cur.text) < 0) {
              model_list.push(cur.text);
              return [...pre, cur];
            }
            return pre;
          } else {
            if (model_list.indexOf(cur.text + ":" + cur.input_value) < 0) {
              model_list.push(cur.text + ":" + cur.input_value);
              return [
                ...pre,
                {
                  text: cur.text + ":" + cur.input_value,
                },
              ];
            }
            return pre;
          }
        }, []);
      }
    },
    filter(item, queryText, itemText) {
      if (item.header) return false;

      const hasValue = (val) => (val != null ? val : "");

      const text = hasValue(itemText);
      const query = hasValue(queryText);

      return (
        text.toString().toLowerCase().indexOf(query.toString().toLowerCase()) >
        -1
      );
    },
  },
};
</script>
<style>
.v-text-field__slot {
  width: 140px;
}
.inventory {
  padding-left: 4px;
  padding-right: 4px;
}
</style>